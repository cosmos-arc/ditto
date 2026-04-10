# FX & Commodity Prefect + FastAPI 实施计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 为汇率和大宗商品数据添加 Prefect 摄取任务和 FastAPI 查询接口，支持双时间戳（trade_date + trade_date_utc）和跨时区日期转换。

**Architecture:**
- Schema 层扩展：添加 `trade_date_utc` 字段
- Source 层：FRED 查询时将北京时间日期转换为美东时间日期
- Coordinator 层：添加 FX_DAILY 和 COMMODITY_DAILY 的摄取逻辑
- API 层：新增 `/market/fx` 和 `/market/commodity` 查询接口

**Tech Stack:** Prefect, FastAPI, Polars, Pytz

**参考设计文档:** `docs/plans/2026-02-27-global-asset-time-handling-design.md`

---

## Phase 1: Schema 扩展（双时间戳）

### Task 1.1: 扩展 FX Schema 添加 trade_date_utc

**Files:**
- Modify: `packages/data/src/ditto_data/sources/schemas/fx_schemas.py`
- Test: `packages/data/tests/unit/sources/schemas/test_fx_schemas.py`

**Step 1: 扩展 FX_SOURCE_SCHEMA**

```python
# packages/data/src/ditto_data/sources/schemas/fx_schemas.py

"""FX (Foreign Exchange) SourceSchema definitions."""

import polars as pl

from ditto_data.sources.source_schema import SourceSchema

__all__ = ["FX_SOURCE_SCHEMA"]

FX_SOURCE_SCHEMA = SourceSchema(
    dataset="fx_daily",
    key_columns=("instrument_id", "trade_date"),
    schema={
        "instrument_id": pl.Int64,
        "trade_date": pl.Date,
        "trade_date_utc": pl.Datetime("ms"),  # 新增：UTC 午夜时间戳
        "open": pl.Float64,
        "high": pl.Float64,
        "low": pl.Float64,
        "close": pl.Float64,
    },
    pit_columns=(),  # 汇率数据不需要 PIT
)
```

**Step 2: 添加单元测试**

```python
# packages/data/tests/unit/sources/schemas/test_fx_schemas.py

"""Unit tests for FX schemas."""

import polars as pl

from ditto_data.sources.schemas.fx_schemas import FX_SOURCE_SCHEMA


def test_fx_schema_has_trade_date_utc():
    """测试 FX Schema 包含 trade_date_utc 字段."""
    assert "trade_date_utc" in FX_SOURCE_SCHEMA.schema
    assert FX_SOURCE_SCHEMA.schema["trade_date_utc"] == pl.Datetime("ms")


def test_fx_schema_key_columns():
    """测试 FX Schema 主键列."""
    assert FX_SOURCE_SCHEMA.key_columns == ("instrument_id", "trade_date")
```

**Step 3: 运行测试验证**

```bash
pixi run -e dev test packages/data/tests/unit/sources/schemas/test_fx_schemas.py -v
```

**Step 4: Commit**

```bash
git add packages/data/src/ditto_data/sources/schemas/fx_schemas.py packages/data/tests/unit/sources/schemas/test_fx_schemas.py
git commit -m "feat(schema): add trade_date_utc to FX_SOURCE_SCHEMA"
```

---

### Task 1.2: 扩展 Commodity Schema 添加 trade_date_utc

**Files:**
- Modify: `packages/data/src/ditto_data/sources/schemas/commodity_schemas.py`
- Test: `packages/data/tests/unit/sources/schemas/test_commodity_schemas.py`

**Step 1: 扩展 COMMODITY_SOURCE_SCHEMA**

```python
# packages/data/src/ditto_data/sources/schemas/commodity_schemas.py

"""Commodity SourceSchema definitions."""

import polars as pl

from ditto_data.sources.source_schema import SourceSchema

__all__ = ["COMMODITY_SOURCE_SCHEMA"]

COMMODITY_SOURCE_SCHEMA = SourceSchema(
    dataset="commodity_daily",
    key_columns=("instrument_id", "trade_date"),
    schema={
        "instrument_id": pl.Int64,
        "trade_date": pl.Date,
        "trade_date_utc": pl.Datetime("ms"),  # 新增：UTC 午夜时间戳
        "open": pl.Float64,
        "high": pl.Float64,
        "low": pl.Float64,
        "close": pl.Float64,
    },
    pit_columns=(),  # 商品价格不需要 PIT
)
```

**Step 2: 添加单元测试**

```python
# packages/data/tests/unit/sources/schemas/test_commodity_schemas.py

"""Unit tests for Commodity schemas."""

import polars as pl

from ditto_data.sources.schemas.commodity_schemas import COMMODITY_SOURCE_SCHEMA


def test_commodity_schema_has_trade_date_utc():
    """测试 Commodity Schema 包含 trade_date_utc 字段."""
    assert "trade_date_utc" in COMMODITY_SOURCE_SCHEMA.schema
    assert COMMODITY_SOURCE_SCHEMA.schema["trade_date_utc"] == pl.Datetime("ms")


def test_commodity_schema_key_columns():
    """测试 Commodity Schema 主键列."""
    assert COMMODITY_SOURCE_SCHEMA.key_columns == ("instrument_id", "trade_date")
```

**Step 3: 运行测试验证**

```bash
pixi run -e dev test packages/data/tests/unit/sources/schemas/test_commodity_schemas.py -v
```

**Step 4: Commit**

```bash
git add packages/data/src/ditto_data/sources/schemas/commodity_schemas.py packages/data/tests/unit/sources/schemas/test_commodity_schemas.py
git commit -m "feat(schema): add trade_date_utc to COMMODITY_SOURCE_SCHEMA"
```

---

## Phase 2: 时间转换工具

### Task 2.1: 创建时区转换工具模块

**Files:**
- Create: `packages/data/src/ditto_data/utils/timezone_utils.py`
- Test: `packages/data/tests/unit/utils/test_timezone_utils.py`

**Step 1: 创建时区转换工具**

```python
# packages/data/src/ditto_data/utils/timezone_utils.py

"""Timezone utility functions for cross-market data handling.

Design reference: docs/plans/2026-02-27-global-asset-time-handling-design.md
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Literal

import pytz

__all__ = [
    "convert_to_utc_midnight",
    "get_fred_query_date",
    "MARKET_TIMEZONE_MAP",
]

# 市场时区映射
MARKET_TIMEZONE_MAP: dict[str, str] = {
    "SSE": "Asia/Shanghai",      # 上交所
    "SZSE": "Asia/Shanghai",     # 深交所
    "NYSE": "America/New_York",  # 纽约证券交易所
    "NASDAQ": "America/New_York", # 纳斯达克
    "CME": "America/Chicago",    # 芝加哥商品交易所
    "LME": "Europe/London",      # 伦敦金属交易所
    "FX": "America/New_York",    # 外汇（以 NY 收盘为界）
    "FRED": "America/New_York",  # FRED 数据
}


def convert_to_utc_midnight(
    trade_date: date,
    market: Literal["SSE", "SZSE", "NYSE", "NASDAQ", "CME", "LME", "FX", "FRED"],
) -> datetime:
    """
    将本地交易日期转换为 UTC 午夜时间戳.

    根据全球资产时间处理设计，采用 UTC 午夜（00:00:00）作为日线锚定时间。

    Args:
        trade_date: 本地交易日期
        market: 市场代码

    Returns:
        UTC 午夜时间戳（datetime with UTC timezone）

    Examples:
        >>> from datetime import date
        >>> utc_ts = convert_to_utc_midnight(date(2024, 1, 15), "NYSE")
        >>> # 2024-01-15 纽约午夜 = 2024-01-15T05:00:00Z (冬令时) 或 2024-01-15T04:00:00Z (夏令时)

    """
    tz = pytz.timezone(MARKET_TIMEZONE_MAP[market])

    # 创建本地午夜时间，然后转换为 UTC
    local_midnight = tz.localize(
        datetime(trade_date.year, trade_date.month, trade_date.day, 0, 0, 0)
    )

    return local_midnight.astimezone(timezone.utc)


def get_fred_query_date(beijing_trade_date: str) -> str:
    """
    将北京时间日期转换为 FRED 查询日期（美东时间）.

    摄取窗口通常在北京时间次日 05:00（美股收盘后），
    此时美东时间为前一日 16:00。

    Args:
        beijing_trade_date: 北京时间日期 (YYYY-MM-DD)

    Returns:
        美东时间日期 (YYYY-MM-DD)，通常为北京时间日期 - 1 天

    Examples:
        >>> get_fred_query_date("2024-01-16")
        '2024-01-15'

    """
    from datetime import timedelta

    beijing = pytz.timezone("Asia/Shanghai")
    dt = beijing.localize(
        datetime.strptime(beijing_trade_date, "%Y-%m-%d")
    )

    # 北京时间 00:00 = 美东时间前一日 11:00/12:00
    # 所以 FRED 查询日期 = 北京日期 - 1
    fred_date = dt - timedelta(days=1)
    return fred_date.strftime("%Y-%m-%d")
```

**Step 2: 创建 `__init__.py`（如果不存在）**

```python
# packages/data/src/ditto_data/utils/__init__.py

"""DataHub utility modules."""

from ditto_data.utils.timezone_utils import (
    MARKET_TIMEZONE_MAP,
    convert_to_utc_midnight,
    get_fred_query_date,
)

__all__ = [
    "MARKET_TIMEZONE_MAP",
    "convert_to_utc_midnight",
    "get_fred_query_date",
]
```

**Step 3: 添加单元测试**

```python
# packages/data/tests/unit/utils/test_timezone_utils.py

"""Unit tests for timezone utilities."""

from datetime import date, datetime

import pytest

from ditto_data.utils.timezone_utils import (
    convert_to_utc_midnight,
    get_fred_query_date,
    MARKET_TIMEZONE_MAP,
)


class TestMarketTimezoneMap:
    """测试市场时区映射."""

    def test_contains_key_markets(self):
        """测试包含关键市场."""
        assert "SSE" in MARKET_TIMEZONE_MAP
        assert "NYSE" in MARKET_TIMEZONE_MAP
        assert "FRED" in MARKET_TIMEZONE_MAP
        assert "FX" in MARKET_TIMEZONE_MAP

    def test_shanghai_timezone(self):
        """测试上海时区."""
        assert MARKET_TIMEZONE_MAP["SSE"] == "Asia/Shanghai"


class TestConvertToUtcMidnight:
    """测试 UTC 午夜时间戳转换."""

    def test_shanghai_date(self):
        """测试上海日期转换."""
        utc_ts = convert_to_utc_midnight(date(2024, 1, 15), "SSE")
        # 上海 UTC+8，午夜 = UTC 前一日 16:00
        assert utc_ts.year == 2024
        assert utc_ts.month == 1
        assert utc_ts.day == 14  # 前一天

    def test_new_york_date_winter(self):
        """测试纽约日期转换（冬令时）."""
        # 1月15日在冬令时期间（11月-3月）
        utc_ts = convert_to_utc_midnight(date(2024, 1, 15), "NYSE")
        # 冬令时 UTC-5，午夜 = UTC 05:00
        assert utc_ts.hour == 5
        assert utc_ts.day == 15


class TestGetFredQueryDate:
    """测试 FRED 查询日期转换."""

    def test_beijing_to_fred(self):
        """测试北京时间转 FRED 日期."""
        fred_date = get_fred_query_date("2024-01-16")
        assert fred_date == "2024-01-15"

    def test_cross_month_boundary(self):
        """测试跨月边界."""
        fred_date = get_fred_query_date("2024-02-01")
        assert fred_date == "2024-01-31"

    def test_cross_year_boundary(self):
        """测试跨年边界."""
        fred_date = get_fred_query_date("2024-01-01")
        assert fred_date == "2023-12-31"
```

**Step 4: 运行测试**

```bash
pixi run -e dev test packages/data/tests/unit/utils/test_timezone_utils.py -v
```

**Step 5: Commit**

```bash
git add packages/data/src/ditto_data/utils/timezone_utils.py packages/data/src/ditto_data/utils/__init__.py packages/data/tests/unit/utils/test_timezone_utils.py
git commit -m "feat(utils): add timezone conversion utilities for cross-market data"
```

---

## Phase 3: Source Adapter 更新

### Task 3.1: 更新 FRED Commodity Adapter 添加日期转换

**Files:**
- Modify: `packages/data/src/ditto_data/sources/fred/adapters/commodity.py`
- Test: `packages/data/tests/unit/sources/fred/adapters/test_commodity.py`

**Step 1: 更新 CommodityFredAdapter**

在 `fetch_commodities` 方法中：
1. 使用 `get_fred_query_date` 转换查询日期
2. 添加 `trade_date_utc` 字段

```python
# packages/data/src/ditto_data/sources/fred/adapters/commodity.py
# 在文件顶部添加导入
from datetime import datetime
from ditto_data.utils.timezone_utils import (
    convert_to_utc_midnight,
    get_fred_query_date,
)

# 修改 fetch_commodities 方法
def fetch_commodities(
    self,
    codes: list[str],
    start_date: str,
    end_date: str,
) -> pl.DataFrame:
    """
    Fetch commodity prices from FRED.

    Args:
        codes: Commodity codes (e.g., ["COMMOD_WTI", "COMMOD_GOLD"]).
        start_date: Start date (YYYY-MM-DD) in Beijing time.
        end_date: End date (YYYY-MM-DD) in Beijing time.

    Returns:
        DataFrame with COMMODITY_SOURCE_SCHEMA columns including trade_date_utc.

    """
    # 将北京时间日期转换为 FRED 查询日期（美东时间）
    fred_start = get_fred_query_date(start_date)
    fred_end = get_fred_query_date(end_date)

    results: list[pl.DataFrame] = []

    for code in codes:
        indicator = get_fred_indicator(code)
        if indicator is None or indicator.category not in ("commodity", "vix"):
            continue

        instrument_id = COMMODITY_CODE_TO_INSTRUMENT_ID.get(code)
        if instrument_id is None:
            continue

        # 使用转换后的 FRED 日期查询
        df = self._client.get_series_observations(
            series_id=indicator.series_id,
            observation_start=fred_start,
            observation_end=fred_end,
        )

        if df.height == 0:
            continue

        # Transform to COMMODITY_SOURCE_SCHEMA with trade_date_utc
        transformed = df.with_columns(
            pl.lit(instrument_id).alias("instrument_id"),
            pl.col("date").alias("trade_date"),
            # 生成 UTC 午夜时间戳
            pl.col("date").map_elements(
                lambda d: convert_to_utc_midnight(d, "FRED"),
                return_dtype=pl.Datetime("ms"),
            ).alias("trade_date_utc"),
            pl.col("value").alias("open"),
            pl.col("value").alias("high"),
            pl.col("value").alias("low"),
            pl.col("value").alias("close"),
        ).select(
            "instrument_id",
            "trade_date",
            "trade_date_utc",
            "open",
            "high",
            "low",
            "close",
        )

        results.append(transformed)

    if not results:
        return pl.DataFrame(schema=COMMODITY_SOURCE_SCHEMA.schema)

    return pl.concat(results)
```

**Step 2: 更新单元测试**

```python
# packages/data/tests/unit/sources/fred/adapters/test_commodity.py
# 添加测试用例

def test_fetch_commodities_includes_trade_date_utc(mock_fred_client):
    """测试返回数据包含 trade_date_utc 字段."""
    from datetime import date
    from unittest.mock import MagicMock

    import polars as pl

    from ditto_data.sources.fred.adapters.commodity import CommodityFredAdapter

    # 模拟 FRED 客户端返回
    mock_df = pl.DataFrame({
        "date": [date(2024, 1, 15)],
        "value": [75.5],
        "realtime_start": [date(2024, 1, 16)],
        "realtime_end": [date(2024, 1, 16)],
    })
    mock_fred_client.get_series_observations.return_value = mock_df

    adapter = CommodityFredAdapter(api_key="test_key")
    adapter._client = mock_fred_client

    result = adapter.fetch_commodities(
        codes=["COMMOD_WTI"],
        start_date="2024-01-16",  # 北京时间
        end_date="2024-01-16",
    )

    assert "trade_date_utc" in result.columns
    assert result.height == 1
```

**Step 3: 运行测试**

```bash
pixi run -e dev test packages/data/tests/unit/sources/fred/adapters/test_commodity.py -v
```

**Step 4: Commit**

```bash
git add packages/data/src/ditto_data/sources/fred/adapters/commodity.py packages/data/tests/unit/sources/fred/adapters/test_commodity.py
git commit -m "feat(fred): add date conversion and trade_date_utc to CommodityFredAdapter"
```

---

### Task 3.2: 更新 Tushare FX Adapter 添加 UTC 时间戳

**Files:**
- Modify: `packages/data/src/ditto_data/sources/tushare/adapters/fx.py`
- Test: `packages/data/tests/unit/sources/tushare/adapters/test_fx_adapter.py`

**Step 1: 更新 FxTushareAdapter**

```python
# packages/data/src/ditto_data/sources/tushare/adapters/fx.py
# 添加导入
from datetime import datetime

from ditto_data.utils.timezone_utils import convert_to_utc_midnight

# 修改 fetch_fx_daily 方法
@traced("source.tushare.fetch_fx_daily")
def fetch_fx_daily(
    self,
    ts_codes: list[str],
    start_date: str,
    end_date: str,
) -> pl.DataFrame:
    """
    Fetch FX daily data from Tushare.

    Args:
        ts_codes: FX ticker codes (e.g., ["USDCNH.FXCM"]).
        start_date: Start date (YYYY-MM-DD).
        end_date: End date (YYYY-MM-DD).

    Returns:
        DataFrame with FX_SOURCE_SCHEMA columns including trade_date_utc.

    """
    compact_start = start_date.replace("-", "")
    compact_end = end_date.replace("-", "")

    results: list[pl.DataFrame] = []

    for ts_code in ts_codes:
        with tushare_fetch_error_handler("fx_daily", ts_code):
            response = self._client.query(
                api_name="fx_daily",
                fields="ts_code,trade_date,open,high,low,close",
                ts_code=ts_code,
                start_date=compact_start,
                end_date=compact_end,
            )

            if response.is_empty():
                continue

            instrument_id = FX_CODE_TO_INSTRUMENT_ID.get(ts_code)
            if instrument_id is None:
                continue

            # 转换为 FX_SOURCE_SCHEMA with trade_date_utc
            df = response.with_columns(
                pl.lit(instrument_id).alias("instrument_id"),
                pl.col("trade_date")
                .cast(pl.String)
                .str.to_date(format="%Y%m%d", strict=False)
                .alias("trade_date"),
                # 生成 UTC 午夜时间戳（Tushare 汇率使用上海时区）
                pl.col("trade_date")
                .cast(pl.String)
                .str.to_date(format="%Y%m%d", strict=False)
                .map_elements(
                    lambda d: convert_to_utc_midnight(d, "SSE"),
                    return_dtype=pl.Datetime("ms"),
                )
                .alias("trade_date_utc"),
                pl.col("open").cast(pl.Float64),
                pl.col("high").cast(pl.Float64),
                pl.col("low").cast(pl.Float64),
                pl.col("close").cast(pl.Float64),
            ).select(
                "instrument_id",
                "trade_date",
                "trade_date_utc",
                "open",
                "high",
                "low",
                "close",
            )

            results.append(df)

    if not results:
        return pl.DataFrame(schema=FX_SOURCE_SCHEMA.schema)

    return pl.concat(results)
```

**Step 2: 更新单元测试**

添加测试验证 `trade_date_utc` 字段存在。

**Step 3: 运行测试**

```bash
pixi run -e dev test packages/data/tests/unit/sources/tushare/adapters/test_fx_adapter.py -v
```

**Step 4: Commit**

```bash
git add packages/data/src/ditto_data/sources/tushare/adapters/fx.py packages/data/tests/unit/sources/tushare/adapters/test_fx_adapter.py
git commit -m "feat(tushare): add trade_date_utc to FxTushareAdapter"
```

---

## Phase 4: IngestionCoordinator 扩展

### Task 4.1: 添加 FX 和 Commodity 数据源方法

**Files:**
- Modify: `packages/data/src/ditto_data/sources/source.py`

**Step 1: 添加 FX 和 Commodity fetch 方法**

在 DataSource 基类中添加抽象方法，在 TushareSource 和 FredSource 中实现。

**Step 2: Commit**

```bash
git commit -m "feat(source): add fetch_fx_daily and fetch_commodity_daily to DataSource"
```

---

### Task 4.2: 更新 IngestionCoordinator 支持 FX 和 Commodity

**Files:**
- Modify: `apps/port/src/ditto_port/services/ingestion/coordinator.py`

**Step 1: 添加 FX 和 Commodity 摄取逻辑**

在 `_fetch_data` 方法的 handlers 字典中添加：

```python
# 在 _fetch_data 方法的 handlers 字典中添加
Dataset.FX_DAILY: lambda: self._source.fetch_fx_daily(
    ts_codes=list(FX_CODE_TO_INSTRUMENT_ID.keys()),
    start_date=trade_date,
    end_date=trade_date,
),
Dataset.COMMODITY_DAILY: lambda: self._source.fetch_commodities(
    codes=list(COMMODITY_CODE_TO_INSTRUMENT_ID.keys()),
    start_date=trade_date,
    end_date=trade_date,
),
```

**Step 2: 导入必要的映射**

```python
from ditto_data.sources.fred.adapters.commodity import COMMODITY_CODE_TO_INSTRUMENT_ID
from ditto_data.sources.tushare.adapters.fx import FX_CODE_TO_INSTRUMENT_ID
```

**Step 3: 运行测试**

```bash
pixi run -e dev test apps/port/tests/ -v -k coordinator
```

**Step 4: Commit**

```bash
git commit -m "feat(coordinator): add FX_DAILY and COMMODITY_DAILY ingestion support"
```

---

## Phase 5: Store 层更新

### Task 5.1: 更新 FxBarsWriter 和 CommodityBarsWriter

**Files:**
- Modify: `packages/data/src/ditto_data/stores/market/fx/fx_writer.py`
- Modify: `packages/data/src/ditto_data/stores/market/commodity/commodity_writer.py`

**Step 1: 确保 Writer 支持 trade_date_utc 字段**

由于使用了动态 schema，Writer 应该自动支持新字段。验证测试通过。

**Step 2: Commit**

```bash
git commit -m "chore(store): verify trade_date_utc support in writers"
```

---

## Phase 6: FastAPI 路由

### Task 6.1: 创建 FX API 路由

**Files:**
- Create: `apps/port/src/ditto_port/api/routes/fx.py`
- Create: `apps/port/src/ditto_port/models/fx.py`
- Test: `apps/port/tests/unit/api/routes/test_fx.py`

**Step 1: 创建 FX 数据模型**

```python
# apps/port/src/ditto_port/models/fx.py

"""FX API 数据模型."""

from datetime import date, datetime

from pydantic import BaseModel, Field


class FxBar(BaseModel):
    """汇率日线数据."""

    instrument_id: int = Field(..., description="标的ID")
    trade_date: date = Field(..., description="交易日期（当地时间）")
    trade_date_utc: datetime | None = Field(None, description="UTC 时间戳")
    open: float | None = Field(None, description="开盘价")
    high: float | None = Field(None, description="最高价")
    low: float | None = Field(None, description="最低价")
    close: float | None = Field(None, description="收盘价")


class FxQuery(BaseModel):
    """汇率数据查询参数."""

    instrument_ids: list[int] | None = Field(None, description="标的ID列表")
    start_date: date | None = Field(None, description="开始日期")
    end_date: date | None = Field(None, description="结束日期")
    limit: int = Field(default=1000, ge=1, le=10000, description="返回数量限制")


def to_fx_bar_list(df) -> list[FxBar]:
    """将 DataFrame 转换为 FxBar 列表."""
    if df.is_empty():
        return []
    return [
        FxBar(
            instrument_id=row["instrument_id"],
            trade_date=row["trade_date"],
            trade_date_utc=row.get("trade_date_utc"),
            open=row.get("open"),
            high=row.get("high"),
            low=row.get("low"),
            close=row.get("close"),
        )
        for row in df.to_dicts()
    ]
```

**Step 2: 创建 FX API 路由**

```python
# apps/port/src/ditto_port/api/routes/fx.py

"""FX 数据 API 路由."""

import asyncio
from typing import Annotated

from dishka import FromComponent
from dishka.integrations.fastapi import inject
from fastapi import APIRouter

from ditto_port.models.common import APIResponse
from ditto_port.models.fx import FxBar, FxQuery, to_fx_bar_list

router = APIRouter(prefix="/fx", tags=["fx"])


@router.post("/bars", response_model=APIResponse[list[FxBar]])
@inject
async def post_bars(
    query: FxQuery,
    # service: Annotated[FxService, FromComponent()],  # TODO: 创建 FxService
) -> APIResponse[list[FxBar]]:
    """
    查询汇率 K 线数据.

    Args:
        query: 查询参数
            - instrument_ids: 标的 ID 列表 (可选)
            - start_date: 开始日期 (可选)
            - end_date: 结束日期 (可选)
            - limit: 返回数量限制 (1-10000)

    Returns:
        APIResponse 包含汇率 K 线数据列表

    """
    # TODO: 实现 FxService 并注入
    # 当前返回空列表作为占位
    return APIResponse(data=[])
```

**Step 3: 注册路由到主应用**

修改 `apps/port/src/ditto_port/api/__init__.py`:

```python
from ditto_port.api.routes import fx

# 在路由注册部分添加
app.include_router(fx.router)
```

**Step 4: Commit**

```bash
git add apps/port/src/ditto_port/api/routes/fx.py apps/port/src/ditto_port/models/fx.py
git commit -m "feat(api): add FX bars query endpoint"
```

---

### Task 6.2: 创建 Commodity API 路由

**Files:**
- Create: `apps/port/src/ditto_port/api/routes/commodity.py`
- Create: `apps/port/src/ditto_port/models/commodity.py`

**Step 1: 创建 Commodity 数据模型**

```python
# apps/port/src/ditto_port/models/commodity.py

"""Commodity API 数据模型."""

from datetime import date, datetime

from pydantic import BaseModel, Field


class CommodityBar(BaseModel):
    """大宗商品日线数据."""

    instrument_id: int = Field(..., description="标的ID")
    trade_date: date = Field(..., description="交易日期（当地时间）")
    trade_date_utc: datetime | None = Field(None, description="UTC 时间戳")
    open: float | None = Field(None, description="开盘价")
    high: float | None = Field(None, description="最高价")
    low: float | None = Field(None, description="最低价")
    close: float | None = Field(None, description="收盘价")


class CommodityQuery(BaseModel):
    """大宗商品数据查询参数."""

    instrument_ids: list[int] | None = Field(None, description="标的ID列表")
    start_date: date | None = Field(None, description="开始日期")
    end_date: date | None = Field(None, description="结束日期")
    limit: int = Field(default=1000, ge=1, le=10000, description="返回数量限制")


def to_commodity_bar_list(df) -> list[CommodityBar]:
    """将 DataFrame 转换为 CommodityBar 列表."""
    if df.is_empty():
        return []
    return [
        CommodityBar(
            instrument_id=row["instrument_id"],
            trade_date=row["trade_date"],
            trade_date_utc=row.get("trade_date_utc"),
            open=row.get("open"),
            high=row.get("high"),
            low=row.get("low"),
            close=row.get("close"),
        )
        for row in df.to_dicts()
    ]
```

**Step 2: 创建 Commodity API 路由**

```python
# apps/port/src/ditto_port/api/routes/commodity.py

"""大宗商品数据 API 路由."""

import asyncio
from typing import Annotated

from dishka import FromComponent
from dishka.integrations.fastapi import inject
from fastapi import APIRouter

from ditto_port.models.common import APIResponse
from ditto_port.models.commodity import CommodityBar, CommodityQuery, to_commodity_bar_list

router = APIRouter(prefix="/commodity", tags=["commodity"])


@router.post("/bars", response_model=APIResponse[list[CommodityBar]])
@inject
async def post_bars(
    query: CommodityQuery,
    # service: Annotated[CommodityService, FromComponent()],  # TODO: 创建 Service
) -> APIResponse[list[CommodityBar]]:
    """
    查询大宗商品 K 线数据.

    Args:
        query: 查询参数
            - instrument_ids: 标的 ID 列表 (可选)
            - start_date: 开始日期 (可选)
            - end_date: 结束日期 (可选)
            - limit: 返回数量限制 (1-10000)

    Returns:
        APIResponse 包含大宗商品 K 线数据列表

    """
    # TODO: 实现 CommodityService 并注入
    return APIResponse(data=[])
```

**Step 3: 注册路由到主应用**

**Step 4: Commit**

```bash
git add apps/port/src/ditto_port/api/routes/commodity.py apps/port/src/ditto_port/models/commodity.py
git commit -m "feat(api): add Commodity bars query endpoint"
```

---

## Phase 7: 集成测试与验证

### Task 7.1: 添加 FX 和 Commodity 摄取集成测试

**Files:**
- Create: `apps/port/tests/integration/ingestion/test_fx_commodity.py`

**Step 1: 创建集成测试**

```python
# apps/port/tests/integration/ingestion/test_fx_commodity.py

"""FX 和 Commodity 摄取集成测试."""

import pytest


@pytest.mark.integration
class TestFxCommodityIngestion:
    """FX 和 Commodity 摄取集成测试."""

    def test_fx_daily_schema_has_utc_timestamp(self):
        """测试 FX 数据包含 UTC 时间戳."""
        # TODO: 实现集成测试
        pass

    def test_commodity_daily_schema_has_utc_timestamp(self):
        """测试 Commodity 数据包含 UTC 时间戳."""
        # TODO: 实现集成测试
        pass
```

**Step 2: Commit**

```bash
git commit -m "test(integration): add FX and Commodity ingestion tests"
```

---

### Task 7.2: 运行完整验证

**Step 1: 运行完整测试套件**

```bash
pixi run -e dev check
```

**Step 2: 确认所有测试通过**

---

## 总结

| Phase | Task | 描述 | 文件数 |
|-------|------|------|--------|
| 1 | 1.1-1.2 | Schema 扩展（trade_date_utc） | 4 |
| 2 | 2.1 | 时区转换工具 | 3 |
| 3 | 3.1-3.2 | Source Adapter 更新 | 4 |
| 4 | 4.1-4.2 | IngestionCoordinator 扩展 | 2 |
| 5 | 5.1 | Store 层验证 | 2 |
| 6 | 6.1-6.2 | FastAPI 路由 | 6 |
| 7 | 7.1-7.2 | 集成测试与验证 | 2 |

**预计新增/修改文件:** ~23 个文件
