# sources/tushare 目录重构执行计划

**日期**: 2026-01-22
**目标**: 优化 `sources/tushare/` 目录结构，提高代码组织清晰度

---

## 当前问题

```
sources/tushare/
├── base.py            # BaseTushareAdapter (806 bytes)
├── calendar_source.py # CalendarTushareAdapter (1838 bytes)
├── stock_source.py    # StockTushareAdapter (8184 bytes)
├── etf_source.py      # ETFTushareAdapter (4230 bytes)
├── status_merger.py   # StockStatusMerger (6846 bytes) - 职责混杂
├── error_handler.py   # tushare_fetch_error_handler (1994 bytes)
├── transformer.py     # TushareDataTransformer
├── http_utils.py      # HTTP 工具
├── rate_limiter.py    # 限流器
├── client.py          # TushareClient
├── tushare_source.py  # TushareSource 入口 (6852 bytes, 174 行)
└── __init__.py
```

**问题**：
1. 基类、专门源、辅助工具混在同一层级
2. 缺乏清晰的模块边界
3. `status_merger.py` 职责混杂（fetch + merge）
4. 新增数据类型时文件数量持续增长

---

## 目标结构

```
sources/tushare/
├── __init__.py
├── tushare_source.py       # TushareSource 入口 (保持不变)
├── client.py               # TushareClient (保持不变)
├── adapters/               # 适配器层（有状态，与 API 交互）
│   ├── __init__.py
│   ├── base.py            # BaseTushareAdapter
│   ├── calendar.py        # CalendarTushareAdapter
│   ├── stock.py           # StockTushareAdapter
│   ├── etf.py             # ETFTushareAdapter
│   └── stock_status.py    # StockStatusAdapter (从 status_merger 拆分)
├── processors/             # 处理器层（无状态，数据转换/合并）
│   ├── __init__.py
│   ├── transformer.py     # TushareDataTransformer
│   ├── error_handler.py   # tushare_fetch_error_handler
│   └── merger.py          # StatusMerger (从 status_merger 拆分)
└── utils/                  # 工具层（通用工具）
    ├── __init__.py
    ├── http_utils.py      # HTTP 工具
    └── rate_limiter.py    # 限流器
```

**优点**：
- ✅ Clean Architecture: 适配器/处理器/工具三层清晰分离
- ✅ 适配器有状态（持有 client），处理器无状态
- ✅ 易于扩展（新增数据类型只需在 `adapters/` 下添加文件）
- ✅ 职责单一（status_merger 拆分为适配器 + 处理器）

---

## 执行策略

- **方式**: 一次性重构（单次 commit 完成）
- **验证**: 每步运行相关测试确保功能正常
- **回滚**: 如有问题使用 `git reset --hard`

---

## 实施步骤

### Step 1: 创建新目录结构

```bash
cd packages/datahub/src/ditto_datahub/sources/tushare
mkdir -p adapters processors utils
```

### Step 2: 拆分 status_merger.py

**创建 `adapters/stock_status.py`**（StockStatusAdapter - fetch 方法）:

```python
"""股票状态数据适配器."""

from __future__ import annotations

import polars as pl
from ditto_foundation import logger

from ditto_datahub.meta.schemas import (
    TUSHARE_LIST_STATUS_SCHEMA,
    TUSHARE_ST_SCHEMA,
    TUSHARE_SUSPEND_SCHEMA,
)
from ditto_datahub.sources.tushare.client import TushareClient


class StockStatusAdapter:
    """股票状态数据适配器.

    负责从 Tushare API 获取股票的状态数据，包括：
    - 停牌数据 (suspend_d API)
    - ST 状态数据 (stock_st API)
    - 上市状态数据 (stock_basic API)

    Attributes:
        _client: Tushare API 客户端实例.

    """

    def __init__(self, client: TushareClient) -> None:
        """初始化 StockStatusAdapter.

        Args:
            client: Tushare API 客户端实例.

        """
        self._client = client

    def fetch_suspend_data(self, ts_date: str) -> pl.DataFrame:
        """获取停牌数据（从 suspend_d API）.

        Args:
            ts_date: 交易日期 (YYYYMMDD 格式)

        Returns:
            DataFrame with columns: ts_code, suspend_timing
            如果获取失败返回空 DataFrame

        """
        suspend_df = pl.DataFrame(schema=TUSHARE_SUSPEND_SCHEMA)
        try:
            suspend_response = self._client.query(
                api_name="suspend_d",
                suspend_date=ts_date,
                fields="ts_code,suspend_timing",
            )
            if len(suspend_response) > 0:
                suspend_df = suspend_response
        except Exception as e:
            logger.warning(
                "Failed to fetch suspend_d data",
                event="tushare_suspend_d_fetch_error",
                error=str(e),
            )
        return suspend_df

    def fetch_st_data(self) -> pl.DataFrame:
        """获取 ST 状态数据（从 stock_st API）.

        Returns:
            DataFrame with columns: ts_code, name
            如果获取失败返回空 DataFrame

        Note:
            stock_st API 不需要日期参数，返回所有当前 ST 股票.

        """
        st_df = pl.DataFrame(schema=TUSHARE_ST_SCHEMA)
        try:
            st_response = self._client.query(
                api_name="stock_st",
                fields="ts_code,name",
            )
            if len(st_response) > 0:
                st_df = st_response
        except Exception as e:
            logger.warning(
                "Failed to fetch stock_st data",
                event="tushare_stock_st_fetch_error",
                error=str(e),
            )
        return st_df

    def fetch_list_status_data(self) -> pl.DataFrame:
        """获取上市状态数据（从 stock_basic API）.

        Returns:
            DataFrame with columns: ts_code, list_status
            如果获取失败返回空 DataFrame

        Note:
            stock_basic API 不需要日期参数，返回所有股票的上市状态.
            list_status: L=正常, D=退市, P=暂停.

        """
        list_status_df = pl.DataFrame(schema=TUSHARE_LIST_STATUS_SCHEMA)
        try:
            basic_response = self._client.query(
                api_name="stock_basic",
                fields="ts_code,list_status",
            )
            if len(basic_response) > 0:
                list_status_df = basic_response
        except Exception as e:
            logger.warning(
                "Failed to fetch stock_basic list_status",
                event="tushare_stock_basic_fetch_error",
                error=str(e),
            )
        return list_status_df
```

**创建 `processors/merger.py`**（StatusMerger - merge 方法）:

```python
"""数据合并处理器."""

from __future__ import annotations

import polars as pl


class StatusMerger:
    """状态数据合并器.

    负责合并股票的状态数据（list_status + suspend + ST）.

    """

    def merge_status_data(
        self,
        list_status_df: pl.DataFrame,
        suspend_df: pl.DataFrame,
        st_df: pl.DataFrame,
        trade_date: str,
    ) -> pl.DataFrame:
        """合并状态数据（list_status + suspend + ST）.

        Args:
            list_status_df: 上市状态数据 (columns: ts_code, list_status)
            suspend_df: 停牌数据 (columns: ts_code, suspend_timing)
            st_df: ST状态数据 (columns: ts_code, name)
            trade_date: 交易日期 (YYYY-MM-DD 格式)

        Returns:
            DataFrame with columns:
            - src_code: 股票代码
            - trade_date: 交易日期
            - is_suspended: 是否停牌 (Boolean)
            - suspend_timing: 停牌时间段 (String, e.g. "09:30-10:00" or "")
            - is_st: 是否ST (Boolean)
            - st_type: ST类型 (String, e.g. "ST" or "")
            - list_status: 上市状态 (String: L=正常, D=退市, P=暂停)

        """
        # Start with all stock codes from list_status (as reference)
        result = list_status_df.rename({"ts_code": "src_code"})

        # Add suspension info
        if not suspend_df.is_empty():
            suspend_expanded = suspend_df.with_columns(
                pl.lit(True).alias("is_suspended")
            )
            result = result.join(
                suspend_expanded.rename({"ts_code": "src_code"}),
                on="src_code",
                how="left",
            )
        else:
            result = result.with_columns(pl.lit(None).alias("is_suspended"))
            result = result.with_columns(pl.lit(None).alias("suspend_timing"))

        # Add ST status
        if not st_df.is_empty():
            st_expanded = st_df.with_columns(
                pl.lit(True).alias("is_st"),
                pl.col("name").alias("st_type"),
            )
            result = result.join(
                st_expanded.rename({"ts_code": "src_code"}),
                on="src_code",
                how="left",
            )
        else:
            result = result.with_columns(pl.lit(None).alias("is_st"))
            result = result.with_columns(pl.lit(None).alias("st_type"))

        # Fill null values with defaults
        result = result.with_columns(
            pl.col("is_suspended").fill_null(False),
            pl.col("suspend_timing").fill_null(""),
            pl.col("is_st").fill_null(False),
            pl.col("st_type").fill_null(""),
            pl.col("list_status").fill_null("L"),  # Default to 正常
        )

        # Add trade_date column
        result = result.with_columns(
            pl.lit(trade_date).str.to_date("%Y-%m-%d").alias("trade_date")
        )

        # Select and reorder columns
        result = result.select(
            "src_code",
            "trade_date",
            "is_suspended",
            "suspend_timing",
            "is_st",
            "st_type",
            "list_status",
        )

        return result
```

### Step 3: 移动并重命名适配器文件

```bash
# 移动到 adapters/ 并重命名
mv base.py adapters/base.py
mv calendar_source.py adapters/calendar.py
mv stock_source.py adapters/stock.py
mv etf_source.py adapters/etf.py
```

### Step 4: 移动处理器文件

```bash
# 移动到 processors/
mv transformer.py processors/transformer.py
mv error_handler.py processors/error_handler.py
```

### Step 5: 移动工具文件

```bash
# 移动到 utils/
mv http_utils.py utils/http_utils.py
mv rate_limiter.py utils/rate_limiter.py
```

### Step 6: 更新适配器类名（*Source → *Adapter）

**需要重命名的类**：
- `BaseTushareAdapter` → `BaseTushareAdapter`
- `CalendarTushareAdapter` → `CalendarTushareAdapter`
- `StockTushareAdapter` → `StockTushareAdapter`
- `ETFTushareAdapter` → `ETFTushareAdapter`

### Step 7: 创建 __init__.py 文件

**`adapters/__init__.py`**:
```python
from ditto_datahub.sources.tushare.adapters.base import BaseTushareAdapter
from ditto_datahub.sources.tushare.adapters.calendar import CalendarTushareAdapter
from ditto_datahub.sources.tushare.adapters.etf import ETFTushareAdapter
from ditto_datahub.sources.tushare.adapters.stock import StockTushareAdapter
from ditto_datahub.sources.tushare.adapters.stock_status import StockStatusAdapter

__all__ = [
    "BaseTushareAdapter",
    "CalendarTushareAdapter",
    "ETFTushareAdapter",
    "StockTushareAdapter",
    "StockStatusAdapter",
]
```

**`processors/__init__.py`**:
```python
from ditto_datahub.sources.tushare.processors.error_handler import (
    tushare_fetch_error_handler,
)
from ditto_datahub.sources.tushare.processors.merger import StatusMerger
from ditto_datahub.sources.tushare.processors.transformer import (
    ADJ_FACTOR_MAPPING,
    CALENDAR_MAPPING,
    DAILY_OHLCV_MAPPING,
    ETF_BASIC_MAPPING,
    FUND_ADJ_MAPPING,
    STOCK_BASIC_MAPPING,
    STOCK_LIMIT_MAPPING,
    ColumnMapping,
    TushareDataTransformer,
)

__all__ = [
    "tushare_fetch_error_handler",
    "StatusMerger",
    "TushareDataTransformer",
    "ColumnMapping",
    # Mappings
    "ADJ_FACTOR_MAPPING",
    "CALENDAR_MAPPING",
    "DAILY_OHLCV_MAPPING",
    "ETF_BASIC_MAPPING",
    "FUND_ADJ_MAPPING",
    "STOCK_BASIC_MAPPING",
    "STOCK_LIMIT_MAPPING",
]
```

**`utils/__init__.py`**:
```python
from ditto_datahub.sources.tushare.utils.http_utils import (
    DEFAULT_HEADERS,
    HTTPClientMixin,
)
from ditto_datahub.sources.tushare.utils.rate_limiter import (
    RateLimiter,
    TokenBucketRateLimiter,
)

__all__ = [
    "DEFAULT_HEADERS",
    "HTTPClientMixin",
    "RateLimiter",
    "TokenBucketRateLimiter",
]
```

### Step 8: 更新导入语句

**需要更新的文件**：
1. `tushare_source.py` - 更新适配器导入
2. `adapters/stock.py` - 更新 status_merger 导入为 StockStatusAdapter + StatusMerger
3. `adapters/calendar.py` - 更新基类导入
4. `adapters/etf.py` - 更新基类导入
5. `processors/error_handler.py` - 更新 client 导入
6. `processors/transformer.py` - 更新相关导入
7. `conftest.py` - 更新测试导入
8. 所有测试文件 - 更新导入路径

### Step 9: 删除旧文件

```bash
rm status_merger.py
```

### Step 10: 验证测试

```bash
# 类型检查
pixi run -e dev type packages/datahub/src/ditto_datahub/sources/tushare/

# 单元测试
pixi run -e dev pytest packages/datahub/tests/unit/sources/tushare/ -v

# 集成测试
pixi run -e dev pytest packages/datahub/tests/integration/sources/tushare/ -v
```

---

## 导入路径变化

```python
# 之前
from ditto_datahub.sources.tushare.base import BaseTushareAdapter
from ditto_datahub.sources.tushare.calendar_source import CalendarTushareAdapter
from ditto_datahub.sources.tushare.stock_source import StockTushareAdapter
from ditto_datahub.sources.tushare.etf_source import ETFTushareAdapter
from ditto_datahub.sources.tushare.status_merger import StockStatusMerger
from ditto_datahub.sources.tushare.error_handler import tushare_fetch_error_handler
from ditto_datahub.sources.tushare.transformer import TushareDataTransformer

# 之后
from ditto_datahub.sources.tushare.adapters.base import BaseTushareAdapter
from ditto_datahub.sources.tushare.adapters.calendar import CalendarTushareAdapter
from ditto_datahub.sources.tushare.adapters.stock import StockTushareAdapter
from ditto_datahub.sources.tushare.adapters.etf import ETFTushareAdapter
from ditto_datahub.sources.tushare.adapters.stock_status import StockStatusAdapter
from ditto_datahub.sources.tushare.processors.merger import StatusMerger
from ditto_datahub.sources.tushare.processors.error_handler import tushare_fetch_error_handler
from ditto_datahub.sources.tushare.processors.transformer import TushareDataTransformer
```

---

## 时间估算

- 创建目录: 2 分钟
- 拆分 status_merger.py: 5 分钟
- 移动文件: 3 分钟
- 更新类名: 5 分钟
- 创建 __init__.py: 5 分钟
- 更新导入语句: 15 分钟
- 删除旧文件: 1 分钟
- 运行验证: 10 分钟
- **总计**: 约 45 分钟
