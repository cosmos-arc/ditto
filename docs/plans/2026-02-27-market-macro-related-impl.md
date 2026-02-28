# Market 域宏观相关数据实施计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 实现 Market 域宏观相关数据（利率/汇率/大宗商品/VIX）的摄取、存储和 CLI 命令

**Architecture:** 混合存储模式 - 利率复用现有 Macro 存储（单值模式），汇率/商品/VIX 使用独立 OHLC 存储。遵循现有 Tushare/FRED 适配器模式。

**Tech Stack:** Python 3.12+, Polars, Typer CLI, Parquet 存储

**Design Doc:** [2026-02-26-market-domain-macro-related-design.md](2026-02-26-market-domain-macro-related-design.md)

---

## Phase 1: 基础设施扩展 `[S]`

### Task 1.1: 扩展 FRED 利率指标定义

**Files:**
- Modify: `packages/datahub/src/ditto_datahub/sources/fred/indicators.py:43-128`

**Step 1: Write the failing test**

```python
# packages/datahub/tests/unit/sources/fred/test_indicators.py

def test_rate_indicators_exist() -> None:
    """测试美国利率指标定义存在."""
    from ditto_datahub.sources.fred.indicators import get_fred_indicator

    # 美国国债收益率
    assert get_fred_indicator("US_BOND_YIELD_1Y") is not None
    assert get_fred_indicator("US_BOND_YIELD_2Y") is not None
    assert get_fred_indicator("US_BOND_YIELD_5Y") is not None
    assert get_fred_indicator("US_BOND_YIELD_10Y") is not None
    assert get_fred_indicator("US_BOND_YIELD_30Y") is not None

    # 利差
    assert get_fred_indicator("US_BOND_SPREAD_10Y2Y") is not None

    # 联邦基金利率
    assert get_fred_indicator("US_FEDFUNDS_M") is not None
    assert get_fred_indicator("US_FEDFUNDS_D") is not None


def test_commodity_indicators_exist() -> None:
    """测试大宗商品指标定义存在."""
    from ditto_datahub.sources.fred.indicators import get_fred_indicator

    # 能源
    assert get_fred_indicator("COMMOD_WTI") is not None
    assert get_fred_indicator("COMMOD_BRENT") is not None

    # 贵金属
    assert get_fred_indicator("COMMOD_GOLD") is not None
    assert get_fred_indicator("COMMOD_SILVER") is not None


def test_vix_indicators_exist() -> None:
    """测试 VIX 指标定义存在."""
    from ditto_datahub.sources.fred.indicators import get_fred_indicator

    assert get_fred_indicator("VIX_30D") is not None
    assert get_fred_indicator("VIX_9D") is not None
```

**Step 2: Run test to verify it fails**

```bash
pixi run -e dev pytest packages/datahub/tests/unit/sources/fred/test_indicators.py -v
```
Expected: FAIL with "None" (indicators not found)

**Step 3: Write minimal implementation**

在 `FRED_INDICATORS` 字典中添加利率/商品/VIX 指标定义：

```python
# 在 FRED_INDICATORS 字典末尾添加（约第 128 行后）

    # === Interest Rate (Market Domain) ===
    "US_BOND_YIELD_1Y": FredIndicator(
        series_id="DGS1",
        code="US_BOND_YIELD_1Y",
        name="美国1年期国债收益率",
        category="interest_rate",
        frequency="daily",
        unit="%",
        description="1-Year Treasury Constant Maturity Rate",
        need_pit=False,
    ),
    "US_BOND_YIELD_2Y": FredIndicator(
        series_id="DGS2",
        code="US_BOND_YIELD_2Y",
        name="美国2年期国债收益率",
        category="interest_rate",
        frequency="daily",
        unit="%",
        description="2-Year Treasury Constant Maturity Rate",
        need_pit=False,
    ),
    "US_BOND_YIELD_5Y": FredIndicator(
        series_id="DGS5",
        code="US_BOND_YIELD_5Y",
        name="美国5年期国债收益率",
        category="interest_rate",
        frequency="daily",
        unit="%",
        description="5-Year Treasury Constant Maturity Rate",
        need_pit=False,
    ),
    "US_BOND_YIELD_10Y": FredIndicator(
        series_id="DGS10",
        code="US_BOND_YIELD_10Y",
        name="美国10年期国债收益率",
        category="interest_rate",
        frequency="daily",
        unit="%",
        description="10-Year Treasury Constant Maturity Rate",
        need_pit=False,
    ),
    "US_BOND_YIELD_30Y": FredIndicator(
        series_id="DGS30",
        code="US_BOND_YIELD_30Y",
        name="美国30年期国债收益率",
        category="interest_rate",
        frequency="daily",
        unit="%",
        description="30-Year Treasury Constant Maturity Rate",
        need_pit=False,
    ),
    "US_BOND_SPREAD_10Y2Y": FredIndicator(
        series_id="T10Y2Y",
        code="US_BOND_SPREAD_10Y2Y",
        name="美国10Y-2Y国债利差",
        category="interest_rate",
        frequency="daily",
        unit="%",
        description="10-Year Treasury Minus 2-Year Treasury",
        need_pit=False,
    ),
    "US_FEDFUNDS_M": FredIndicator(
        series_id="FEDFUNDS",
        code="US_FEDFUNDS_M",
        name="美国联邦基金利率(月)",
        category="interest_rate",
        frequency="monthly",
        unit="%",
        description="Effective Federal Funds Rate (Monthly)",
        need_pit=False,
    ),
    "US_FEDFUNDS_D": FredIndicator(
        series_id="DFF",
        code="US_FEDFUNDS_D",
        name="美国联邦基金利率(日)",
        category="interest_rate",
        frequency="daily",
        unit="%",
        description="Effective Federal Funds Rate (Daily)",
        need_pit=False,
    ),
    # === Commodity (Market Domain) ===
    "COMMOD_WTI": FredIndicator(
        series_id="DCOILWTICO",
        code="COMMOD_WTI",
        name="WTI原油",
        category="commodity",
        frequency="daily",
        unit="美元/桶",
        description="Crude Oil Prices: West Texas Intermediate (WTI)",
        need_pit=False,
    ),
    "COMMOD_BRENT": FredIndicator(
        series_id="DCOILBRENTEU",
        code="COMMOD_BRENT",
        name="布伦特原油",
        category="commodity",
        frequency="daily",
        unit="美元/桶",
        description="Crude Oil Prices: Brent - Europe",
        need_pit=False,
    ),
    "COMMOD_GOLD": FredIndicator(
        series_id="GOLDAMGBD228NLBM",
        code="COMMOD_GOLD",
        name="伦敦金",
        category="commodity",
        frequency="daily",
        unit="美元/盎司",
        description="Gold Fixing Price 10:30 A.M. (London market)",
        need_pit=False,
    ),
    "COMMOD_SILVER": FredIndicator(
        series_id="SLVPRUSD",
        code="COMMOD_SILVER",
        name="伦敦银",
        category="commodity",
        frequency="daily",
        unit="美分/盎司",
        description="Silver Fixing Price (London market)",
        need_pit=False,
    ),
    # === VIX (Market Domain) ===
    "VIX_30D": FredIndicator(
        series_id="VIXCLS",
        code="VIX_30D",
        name="VIX波动率指数(30天)",
        category="vix",
        frequency="daily",
        unit="指数",
        description="CBOE Volatility Index (VIX)",
        need_pit=False,
    ),
    "VIX_9D": FredIndicator(
        series_id="VIX9D",
        code="VIX_9D",
        name="VIX波动率指数(9天)",
        category="vix",
        frequency="daily",
        unit="指数",
        description="CBOE 9-Day Volatility Index",
        need_pit=False,
    ),
```

同时更新 `CategoryType` 以包含新类别：

```python
CategoryType = Literal[
    "economic", "prices", "money_supply", "employment", "credit", "survey",
    "interest_rate", "commodity", "vix"  # 新增
]
```

**Step 4: Run test to verify it passes**

```bash
pixi run -e dev pytest packages/datahub/tests/unit/sources/fred/test_indicators.py -v
```
Expected: PASS

**Step 5: Commit**

```bash
git add packages/datahub/src/ditto_datahub/sources/fred/indicators.py packages/datahub/tests/unit/sources/fred/test_indicators.py
git commit -m "feat(datahub): 新增 FRED 利率/商品/VIX 指标定义

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

### Task 1.2: 扩展 Tushare 利率指标定义

**Files:**
- Modify: `packages/datahub/src/ditto_datahub/sources/tushare/processors/mappings/macro.py:43-145`

**Step 1: Write the failing test**

```python
# packages/datahub/tests/unit/sources/tushare/test_macro_indicators.py

def test_cn_rate_indicators_exist() -> None:
    """测试中国利率指标定义存在."""
    from ditto_datahub.sources.tushare.processors.mappings.macro import (
        get_tushare_macro_indicator,
    )

    # Shibor 全期限
    assert get_tushare_macro_indicator("CN_SHIBOR_ON") is not None
    assert get_tushare_macro_indicator("CN_SHIBOR_1W") is not None
    assert get_tushare_macro_indicator("CN_SHIBOR_1M") is not None
    assert get_tushare_macro_indicator("CN_SHIBOR_3M") is not None
    assert get_tushare_macro_indicator("CN_SHIBOR_6M") is not None
    assert get_tushare_macro_indicator("CN_SHIBOR_1Y") is not None

    # LPR
    assert get_tushare_macro_indicator("CN_LPR_1Y") is not None
    assert get_tushare_macro_indicator("CN_LPR_5Y") is not None

    # Libor/Hibor
    assert get_tushare_macro_indicator("CN_LIBOR_USD") is not None
    assert get_tushare_macro_indicator("CN_HIBOR_ON") is not None
```

**Step 2: Run test to verify it fails**

```bash
pixi run -e dev pytest packages/datahub/tests/unit/sources/tushare/test_macro_indicators.py -v
```
Expected: FAIL

**Step 3: Write minimal implementation**

在 `TUSHARE_MACRO_INDICATORS` 字典中添加中国利率指标：

```python
# 在 TUSHARE_MACRO_INDICATORS 字典末尾添加

    # === Interest Rate (Shibor 全期限) ===
    "CN_SHIBOR_ON": TushareMacroIndicator(
        api_name="shibor",
        code="CN_SHIBOR_ON",
        field="on",
        name="隔夜Shibor",
        category="interest_rate",
        frequency="daily",
        unit="%",
        description="上海银行间同业拆放利率隔夜",
        need_pit=False,
        release_lag_days=0,
    ),
    "CN_SHIBOR_1W": TushareMacroIndicator(
        api_name="shibor",
        code="CN_SHIBOR_1W",
        field="1w",
        name="1周Shibor",
        category="interest_rate",
        frequency="daily",
        unit="%",
        description="上海银行间同业拆放利率1周",
        need_pit=False,
        release_lag_days=0,
    ),
    "CN_SHIBOR_2W": TushareMacroIndicator(
        api_name="shibor",
        code="CN_SHIBOR_2W",
        field="2w",
        name="2周Shibor",
        category="interest_rate",
        frequency="daily",
        unit="%",
        description="上海银行间同业拆放利率2周",
        need_pit=False,
        release_lag_days=0,
    ),
    "CN_SHIBOR_1M": TushareMacroIndicator(
        api_name="shibor",
        code="CN_SHIBOR_1M",
        field="1m",
        name="1个月Shibor",
        category="interest_rate",
        frequency="daily",
        unit="%",
        description="上海银行间同业拆放利率1个月",
        need_pit=False,
        release_lag_days=0,
    ),
    "CN_SHIBOR_3M": TushareMacroIndicator(
        api_name="shibor",
        code="CN_SHIBOR_3M",
        field="3m",
        name="3个月Shibor",
        category="interest_rate",
        frequency="daily",
        unit="%",
        description="上海银行间同业拆放利率3个月",
        need_pit=False,
        release_lag_days=0,
    ),
    "CN_SHIBOR_6M": TushareMacroIndicator(
        api_name="shibor",
        code="CN_SHIBOR_6M",
        field="6m",
        name="6个月Shibor",
        category="interest_rate",
        frequency="daily",
        unit="%",
        description="上海银行间同业拆放利率6个月",
        need_pit=False,
        release_lag_days=0,
    ),
    "CN_SHIBOR_9M": TushareMacroIndicator(
        api_name="shibor",
        code="CN_SHIBOR_9M",
        field="9m",
        name="9个月Shibor",
        category="interest_rate",
        frequency="daily",
        unit="%",
        description="上海银行间同业拆放利率9个月",
        need_pit=False,
        release_lag_days=0,
    ),
    "CN_SHIBOR_1Y": TushareMacroIndicator(
        api_name="shibor",
        code="CN_SHIBOR_1Y",
        field="1y",
        name="1年Shibor",
        category="interest_rate",
        frequency="daily",
        unit="%",
        description="上海银行间同业拆放利率1年",
        need_pit=False,
        release_lag_days=0,
    ),
    # === LPR ===
    "CN_LPR_1Y": TushareMacroIndicator(
        api_name="shibor_lpr",
        code="CN_LPR_1Y",
        field="lpr_1y",
        name="1年期LPR",
        category="interest_rate",
        frequency="monthly",
        unit="%",
        description="贷款市场报价利率1年期",
        need_pit=False,
        release_lag_days=0,
    ),
    "CN_LPR_5Y": TushareMacroIndicator(
        api_name="shibor_lpr",
        code="CN_LPR_5Y",
        field="lpr_5y",
        name="5年期LPR",
        category="interest_rate",
        frequency="monthly",
        unit="%",
        description="贷款市场报价利率5年期",
        need_pit=False,
        release_lag_days=0,
    ),
    # === Libor ===
    "CN_LIBOR_USD": TushareMacroIndicator(
        api_name="libor",
        code="CN_LIBOR_USD",
        field="usd",
        name="美元Libor",
        category="interest_rate",
        frequency="daily",
        unit="%",
        description="伦敦银行间同业拆放利率美元",
        need_pit=False,
        release_lag_days=0,
    ),
    # === Hibor ===
    "CN_HIBOR_ON": TushareMacroIndicator(
        api_name="hibor",
        code="CN_HIBOR_ON",
        field="on",
        name="隔夜Hibor",
        category="interest_rate",
        frequency="daily",
        unit="%",
        description="香港银行间同业拆放利率隔夜",
        need_pit=False,
        release_lag_days=0,
    ),
```

更新 `category` 类型：

```python
category: Literal[
    "economic", "prices", "money_supply", "employment", "credit", "survey",
    "interest_rate"  # 新增
]
```

**Step 4: Run test to verify it passes**

```bash
pixi run -e dev pytest packages/datahub/tests/unit/sources/tushare/test_macro_indicators.py -v
```
Expected: PASS

**Step 5: Commit**

```bash
git add packages/datahub/src/ditto_datahub/sources/tushare/processors/mappings/macro.py packages/datahub/tests/unit/sources/tushare/test_macro_indicators.py
git commit -m "feat(datahub): 新增 Tushare 利率指标定义 (Shibor/LPR/Libor/Hibor)

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Phase 2: 利率数据摄取 `[M]`

### Task 2.1: 验证利率数据摄取（复用现有 Macro 流程）

**Files:**
- Test: `packages/datahub/tests/integration/sources/fred/test_rate_ingestion.py`

**Step 1: Write integration test**

```python
# packages/datahub/tests/integration/sources/fred/test_rate_ingestion.py

import polars as pl
import pytest

from ditto_datahub.sources.fred.adapters.macro import MacroFredAdapter


@pytest.mark.skipif(
    not os.environ.get("FRED_API_KEY"),
    reason="FRED_API_KEY not set"
)
class TestFredRateIngestion:
    """FRED 利率数据摄取集成测试."""

    def test_fetch_us_bond_yield_10y(self) -> None:
        """测试获取美国10年期国债收益率."""
        adapter = MacroFredAdapter()

        df = adapter.fetch_indicators(
            codes=["US_BOND_YIELD_10Y"],
            start_date="2024-01-01",
            end_date="2024-01-31",
        )

        assert df.height > 0
        assert "indicator_code" in df.columns
        assert df.filter(pl.col("indicator_code") == "US_BOND_YIELD_10Y").height > 0

        adapter.close()
```

**Step 2: Run test**

```bash
pixi run -e dev pytest packages/datahub/tests/integration/sources/fred/test_rate_ingestion.py -v
```
Expected: PASS (FRED 适配器已支持通用指标获取)

**Step 3: Commit**

```bash
git add packages/datahub/tests/integration/sources/fred/test_rate_ingestion.py
git commit -m "test(datahub): 新增 FRED 利率数据摄取集成测试

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Phase 3: 汇率数据 `[L]`

### Task 3.1: 创建汇率数据 Schema

**Files:**
- Create: `packages/datahub/src/ditto_datahub/sources/schemas/fx_schemas.py`
- Test: `packages/datahub/tests/unit/sources/schemas/test_fx_schemas.py`

**Step 1: Write the failing test**

```python
# packages/datahub/tests/unit/sources/schemas/test_fx_schemas.py

def test_fx_source_schema_exists() -> None:
    """测试汇率源数据 Schema 存在."""
    from ditto_datahub.sources.schemas.fx_schemas import FX_SOURCE_SCHEMA

    assert FX_SOURCE_SCHEMA.dataset == "fx_daily"
    assert "instrument_id" in FX_SOURCE_SCHEMA.schema
    assert "trade_date" in FX_SOURCE_SCHEMA.schema
    assert "open" in FX_SOURCE_SCHEMA.schema
    assert "high" in FX_SOURCE_SCHEMA.schema
    assert "low" in FX_SOURCE_SCHEMA.schema
    assert "close" in FX_SOURCE_SCHEMA.schema
```

**Step 2: Run test to verify it fails**

```bash
pixi run -e dev pytest packages/datahub/tests/unit/sources/schemas/test_fx_schemas.py -v
```
Expected: FAIL

**Step 3: Write implementation**

```python
# packages/datahub/src/ditto_datahub/sources/schemas/fx_schemas.py
"""FX (Foreign Exchange) SourceSchema definitions."""

import polars as pl

from ditto_datahub.sources.source_schema import SourceSchema

__all__ = ["FX_SOURCE_SCHEMA"]

FX_SOURCE_SCHEMA = SourceSchema(
    dataset="fx_daily",
    key_columns=("instrument_id", "trade_date"),
    schema={
        "instrument_id": pl.Int64,
        "trade_date": pl.Date,
        "open": pl.Float64,
        "high": pl.Float64,
        "low": pl.Float64,
        "close": pl.Float64,
    },
    pit_columns=(),  # 汇率数据不需要 PIT
)
```

**Step 4: Run test to verify it passes**

```bash
pixi run -e dev pytest packages/datahub/tests/unit/sources/schemas/test_fx_schemas.py -v
```
Expected: PASS

**Step 5: Commit**

```bash
git add packages/datahub/src/ditto_datahub/sources/schemas/fx_schemas.py packages/datahub/tests/unit/sources/schemas/test_fx_schemas.py
git commit -m "feat(datahub): 新增汇率数据 Schema 定义

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

### Task 3.2: 创建 Tushare 汇率适配器

**Files:**
- Create: `packages/datahub/src/ditto_datahub/sources/tushare/adapters/fx.py`
- Test: `packages/datahub/tests/unit/sources/tushare/adapters/test_fx.py`

**Step 1: Write the failing test**

```python
# packages/datahub/tests/unit/sources/tushare/adapters/test_fx.py

import polars as pl
import pytest
from unittest.mock import MagicMock, patch

from ditto_datahub.sources.tushare.adapters.fx import FxTushareAdapter


class TestFxTushareAdapter:
    """汇率适配器单元测试."""

    @patch("ditto_datahub.sources.tushare.adapters.fx.TushareClient")
    def test_fetch_fx_daily(self, mock_client_class: MagicMock) -> None:
        """测试获取汇率日线数据."""
        # 准备模拟数据
        mock_client = MagicMock()
        mock_client.query.return_value = pl.DataFrame({
            "ts_code": ["USDCNH.FXCM"],
            "trade_date": ["20240115"],
            "open": [7.1800],
            "high": [7.1900],
            "low": [7.1750],
            "close": [7.1850],
        })
        mock_client_class.return_value = mock_client

        adapter = FxTushareAdapter()
        df = adapter.fetch_fx_daily(
            ts_codes=["USDCNH.FXCM"],
            start_date="2024-01-15",
            end_date="2024-01-15",
        )

        assert df.height == 1
        assert "instrument_id" in df.columns
        assert "trade_date" in df.columns
        assert "close" in df.columns
```

**Step 2: Run test to verify it fails**

```bash
pixi run -e dev pytest packages/datahub/tests/unit/sources/tushare/adapters/test_fx.py -v
```
Expected: FAIL

**Step 3: Write implementation**

```python
# packages/datahub/src/ditto_datahub/sources/tushare/adapters/fx.py
"""Tushare FX (Foreign Exchange) data adapter."""

from __future__ import annotations

import polars as pl
from ditto_infra.foundation import traced

from ditto_datahub.sources.schemas.fx_schemas import FX_SOURCE_SCHEMA
from ditto_datahub.sources.tushare.adapters.base import BaseTushareAdapter
from ditto_datahub.sources.tushare.processors.error_handler import (
    tushare_fetch_error_handler,
)


# 汇率品种代码映射到 instrument_id
# 使用 4M 范围 (4,000,000 - 4,999,999) 作为汇率
FX_CODE_TO_INSTRUMENT_ID: dict[str, int] = {
    "USDCNH.FXCM": 4_000_001,
    "EURUSD.FXCM": 4_000_002,
    "GBPUSD.FXCM": 4_000_003,
    "USDJPY.FXCM": 4_000_004,
    "AUDUSD.FXCM": 4_000_005,
    "USDCAD.FXCM": 4_000_006,
}


class FxTushareAdapter(BaseTushareAdapter):
    """Tushare adapter for FX daily data."""

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
            DataFrame with FX_SOURCE_SCHEMA columns.

        """
        compact_start = start_date.replace("-", "")
        compact_end = end_date.replace("-", "")

        results: list[pl.DataFrame] = []

        for ts_code in ts_codes:
            with tushare_fetch_error_handler("fx_daily", ts_code):
                response = self._client.query(
                    api_name="fx_daily",
                    ts_code=ts_code,
                    start_date=compact_start,
                    end_date=compact_end,
                )

                if response.is_empty():
                    continue

                # 获取 instrument_id
                instrument_id = FX_CODE_TO_INSTRUMENT_ID.get(ts_code)
                if instrument_id is None:
                    continue

                # 转换为 FX_SOURCE_SCHEMA
                df = response.with_columns(
                    pl.lit(instrument_id).alias("instrument_id"),
                    pl.col("trade_date")
                    .cast(pl.String)
                    .str.to_date(format="%Y%m%d", strict=False)
                    .alias("trade_date"),
                    pl.col("open").cast(pl.Float64),
                    pl.col("high").cast(pl.Float64),
                    pl.col("low").cast(pl.Float64),
                    pl.col("close").cast(pl.Float64),
                ).select(
                    "instrument_id",
                    "trade_date",
                    "open",
                    "high",
                    "low",
                    "close",
                )

                results.append(df)

        if not results:
            return pl.DataFrame(schema=FX_SOURCE_SCHEMA.schema)

        return pl.concat(results)


__all__ = ["FxTushareAdapter", "FX_CODE_TO_INSTRUMENT_ID"]
```

**Step 4: Run test to verify it passes**

```bash
pixi run -e dev pytest packages/datahub/tests/unit/sources/tushare/adapters/test_fx.py -v
```
Expected: PASS

**Step 5: Commit**

```bash
git add packages/datahub/src/ditto_datahub/sources/tushare/adapters/fx.py packages/datahub/tests/unit/sources/tushare/adapters/test_fx.py
git commit -m "feat(datahub): 新增 Tushare 汇率数据适配器

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

### Task 3.3: 创建汇率数据存储

**Files:**
- Create: `packages/datahub/src/ditto_datahub/stores/market/fx/__init__.py`
- Create: `packages/datahub/src/ditto_datahub/stores/market/fx/fx_writer.py`
- Create: `packages/datahub/src/ditto_datahub/stores/market/fx/fx_reader.py`
- Test: `packages/datahub/tests/unit/stores/market/fx/test_fx_store.py`

**Step 1: Write the failing test**

```python
# packages/datahub/tests/unit/stores/market/fx/test_fx_store.py

import polars as pl
import pytest
from pathlib import Path
import tempfile

from ditto_datahub.stores.market.fx.fx_writer import FxBarsWriter
from ditto_datahub.stores.market.fx.fx_reader import FxBarsReader


class TestFxStore:
    """汇率存储单元测试."""

    def test_write_and_read_fx_bars(self, tmp_path: Path) -> None:
        """测试写入和读取汇率数据."""
        writer = FxBarsWriter(tmp_path)
        reader = FxBarsReader(tmp_path)

        # 准备测试数据
        df = pl.DataFrame({
            "instrument_id": [4_000_001],
            "trade_date": [pl.date(2024, 1, 15)],
            "open": [7.1800],
            "high": [7.1900],
            "low": [7.1750],
            "close": [7.1850],
        })

        # 写入
        result = writer.write(df, year=2024)
        assert result.rows_written == 1

        # 读取
        read_df = reader.read(start_date="2024-01-01", end_date="2024-01-31")
        assert read_df.height == 1
```

**Step 2: Run test to verify it fails**

```bash
pixi run -e dev pytest packages/datahub/tests/unit/stores/market/fx/test_fx_store.py -v
```
Expected: FAIL

**Step 3: Write implementation**

```python
# packages/datahub/src/ditto_datahub/stores/market/fx/__init__.py
"""FX (Foreign Exchange) store module."""

from ditto_datahub.stores.market.fx.fx_reader import FxBarsReader
from ditto_datahub.stores.market.fx.fx_writer import FxBarsWriter

__all__ = ["FxBarsReader", "FxBarsWriter"]
```

```python
# packages/datahub/src/ditto_datahub/stores/market/fx/fx_writer.py
"""FX bars data writer."""

from __future__ import annotations

from pathlib import Path

import polars as pl

from ditto_datahub.models import OnDuplicate
from ditto_datahub.models.storage import WriteStoreResult
from ditto_datahub.stores.base import ParquetStore, YearlyPartition
from ditto_datahub.sources.schemas.fx_schemas import FX_SOURCE_SCHEMA


class FxBarsWriter:
    """
    Writer for FX daily bars data.

    Storage structure:
        data_root/
            market/fx/bars/
                2024.parquet
                2025.parquet
    """

    def __init__(self, data_root: Path) -> None:
        self._store = ParquetStore(data_root, YearlyPartition())
        self._dataset = "market/fx/bars"

    def write(
        self,
        df: pl.DataFrame,
        year: int,
        on_duplicate: OnDuplicate = OnDuplicate.ERROR,
    ) -> WriteStoreResult:
        """Write FX bars data."""
        return self._store.write(
            self._dataset,
            df,
            on_duplicate.value,
            year=year,
        )


__all__ = ["FxBarsWriter"]
```

```python
# packages/datahub/src/ditto_datahub/stores/market/fx/fx_reader.py
"""FX bars data reader."""

from __future__ import annotations

from pathlib import Path

import polars as pl

from ditto_datahub.stores.base import ParquetStore, YearlyPartition


class FxBarsReader:
    """Reader for FX daily bars data."""

    def __init__(self, data_root: Path) -> None:
        self._store = ParquetStore(data_root, YearlyPartition())
        self._dataset = "market/fx/bars"

    def read(
        self,
        instrument_ids: list[int] | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        """Read FX bars data."""
        return self._store.read(
            self._dataset,
            instrument_ids=instrument_ids,
            start_date=start_date,
            end_date=end_date,
        )


__all__ = ["FxBarsReader"]
```

**Step 4: Run test to verify it passes**

```bash
pixi run -e dev pytest packages/datahub/tests/unit/stores/market/fx/test_fx_store.py -v
```
Expected: PASS

**Step 5: Commit**

```bash
git add packages/datahub/src/ditto_datahub/stores/market/fx/ packages/datahub/tests/unit/stores/market/fx/
git commit -m "feat(datahub): 新增汇率数据存储层

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Phase 4: 大宗商品数据 `[L]`

### Task 4.1: 创建商品数据 Schema

**Files:**
- Create: `packages/datahub/src/ditto_datahub/sources/schemas/commodity_schemas.py`
- Test: `packages/datahub/tests/unit/sources/schemas/test_commodity_schemas.py`

**Step 1: Write the failing test**

```python
# packages/datahub/tests/unit/sources/schemas/test_commodity_schemas.py

def test_commodity_source_schema_exists() -> None:
    """测试商品源数据 Schema 存在."""
    from ditto_datahub.sources.schemas.commodity_schemas import COMMODITY_SOURCE_SCHEMA

    assert COMMODITY_SOURCE_SCHEMA.dataset == "commodity_daily"
    assert "instrument_id" in COMMODITY_SOURCE_SCHEMA.schema
    assert "trade_date" in COMMODITY_SOURCE_SCHEMA.schema
    assert "close" in COMMODITY_SOURCE_SCHEMA.schema
```

**Step 2: Run test to verify it fails**

```bash
pixi run -e dev pytest packages/datahub/tests/unit/sources/schemas/test_commodity_schemas.py -v
```
Expected: FAIL

**Step 3: Write implementation**

```python
# packages/datahub/src/ditto_datahub/sources/schemas/commodity_schemas.py
"""Commodity SourceSchema definitions."""

import polars as pl

from ditto_datahub.sources.source_schema import SourceSchema

__all__ = ["COMMODITY_SOURCE_SCHEMA"]

COMMODITY_SOURCE_SCHEMA = SourceSchema(
    dataset="commodity_daily",
    key_columns=("instrument_id", "trade_date"),
    schema={
        "instrument_id": pl.Int64,
        "trade_date": pl.Date,
        "open": pl.Float64,
        "high": pl.Float64,
        "low": pl.Float64,
        "close": pl.Float64,
    },
    pit_columns=(),  # 商品价格不需要 PIT
)
```

**Step 4: Run test to verify it passes**

```bash
pixi run -e dev pytest packages/datahub/tests/unit/sources/schemas/test_commodity_schemas.py -v
```
Expected: PASS

**Step 5: Commit**

```bash
git add packages/datahub/src/ditto_datahub/sources/schemas/commodity_schemas.py packages/datahub/tests/unit/sources/schemas/test_commodity_schemas.py
git commit -m "feat(datahub): 新增商品数据 Schema 定义

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

### Task 4.2: 创建 FRED 商品适配器

**Files:**
- Create: `packages/datahub/src/ditto_datahub/sources/fred/adapters/commodity.py`
- Test: `packages/datahub/tests/unit/sources/fred/adapters/test_commodity.py`

**Step 1: Write the failing test**

```python
# packages/datahub/tests/unit/sources/fred/adapters/test_commodity.py

import polars as pl
import pytest
from unittest.mock import MagicMock, patch

from ditto_datahub.sources.fred.adapters.commodity import CommodityFredAdapter


class TestCommodityFredAdapter:
    """FRED 商品适配器单元测试."""

    @patch("ditto_datahub.sources.fred.adapters.commodity.FredClient")
    def test_fetch_wti(self, mock_client_class: MagicMock) -> None:
        """测试获取 WTI 原油数据."""
        mock_client = MagicMock()
        mock_client.get_series_observations.return_value = pl.DataFrame({
            "date": [pl.date(2024, 1, 15)],
            "value": [72.50],
            "realtime_start": [pl.date(2024, 1, 15)],
            "realtime_end": [pl.date(2024, 1, 15)],
        })
        mock_client_class.return_value = mock_client

        adapter = CommodityFredAdapter()
        df = adapter.fetch_commodities(
            codes=["COMMOD_WTI"],
            start_date="2024-01-15",
            end_date="2024-01-15",
        )

        assert df.height == 1
        assert "instrument_id" in df.columns
        assert "close" in df.columns
```

**Step 2: Run test to verify it fails**

```bash
pixi run -e dev pytest packages/datahub/tests/unit/sources/fred/adapters/test_commodity.py -v
```
Expected: FAIL

**Step 3: Write implementation**

```python
# packages/datahub/src/ditto_datahub/sources/fred/adapters/commodity.py
"""FRED commodity data adapter."""

from __future__ import annotations

import polars as pl

from ditto_datahub.sources.fred.client import FredClient
from ditto_datahub.sources.fred.indicators import get_fred_indicator
from ditto_datahub.sources.schemas.commodity_schemas import COMMODITY_SOURCE_SCHEMA


# 商品代码映射到 instrument_id
# 使用 5M 范围 (5,000,000 - 5,999,999) 作为商品
COMMODITY_CODE_TO_INSTRUMENT_ID: dict[str, int] = {
    "COMMOD_WTI": 5_000_001,
    "COMMOD_BRENT": 5_000_002,
    "COMMOD_GOLD": 5_000_003,
    "COMMOD_SILVER": 5_000_004,
}


class CommodityFredAdapter:
    """Adapter for fetching commodity prices from FRED API."""

    def __init__(self, api_key: str | None = None) -> None:
        self._client = FredClient(api_key=api_key)

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
            start_date: Start date (YYYY-MM-DD).
            end_date: End date (YYYY-MM-DD).

        Returns:
            DataFrame with COMMODITY_SOURCE_SCHEMA columns.

        """
        results: list[pl.DataFrame] = []

        for code in codes:
            indicator = get_fred_indicator(code)
            if indicator is None or indicator.category not in ("commodity", "vix"):
                continue

            instrument_id = COMMODITY_CODE_TO_INSTRUMENT_ID.get(code)
            if instrument_id is None:
                continue

            df = self._client.get_series_observations(
                series_id=indicator.series_id,
                observation_start=start_date,
                observation_end=end_date,
            )

            if df.height == 0:
                continue

            # 转换为 OHLC 格式（FRED 只提供 close）
            transformed = df.with_columns(
                pl.lit(instrument_id).alias("instrument_id"),
                pl.col("date").alias("trade_date"),
                pl.col("value").alias("open"),
                pl.col("value").alias("high"),
                pl.col("value").alias("low"),
                pl.col("value").alias("close"),
            ).select(
                "instrument_id",
                "trade_date",
                "open",
                "high",
                "low",
                "close",
            )

            results.append(transformed)

        if not results:
            return pl.DataFrame(schema=COMMODITY_SOURCE_SCHEMA.schema)

        return pl.concat(results)

    def close(self) -> None:
        """Close underlying HTTP client."""
        self._client.close()

    def __enter__(self) -> CommodityFredAdapter:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()


__all__ = ["CommodityFredAdapter", "COMMODITY_CODE_TO_INSTRUMENT_ID"]
```

**Step 4: Run test to verify it passes**

```bash
pixi run -e dev pytest packages/datahub/tests/unit/sources/fred/adapters/test_commodity.py -v
```
Expected: PASS

**Step 5: Commit**

```bash
git add packages/datahub/src/ditto_datahub/sources/fred/adapters/commodity.py packages/datahub/tests/unit/sources/fred/adapters/test_commodity.py
git commit -m "feat(datahub): 新增 FRED 商品数据适配器

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

### Task 4.3: 创建商品数据存储

**Files:**
- Create: `packages/datahub/src/ditto_datahub/stores/market/commodity/__init__.py`
- Create: `packages/datahub/src/ditto_datahub/stores/market/commodity/commodity_writer.py`
- Create: `packages/datahub/src/ditto_datahub/stores/market/commodity/commodity_reader.py`
- Test: `packages/datahub/tests/unit/stores/market/commodity/test_commodity_store.py`

参考 Task 3.3 的实现模式，创建商品存储层。

**Step 5: Commit**

```bash
git add packages/datahub/src/ditto_datahub/stores/market/commodity/ packages/datahub/tests/unit/stores/market/commodity/
git commit -m "feat(datahub): 新增商品数据存储层

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Phase 5: CLI 命令集成 `[M]`

### Task 5.1: 扩展 ingest market CLI 命令

**Files:**
- Modify: `apps/port/src/ditto_port/cli/commands/ingest/market.py`
- Modify: `apps/port/src/ditto_port/models/config.py`
- Test: `apps/port/tests/unit/cli/test_market_commands.py`

**Step 1: Write the failing test**

```python
# apps/port/tests/unit/cli/test_market_commands.py

from typer.testing import CliRunner
from ditto_port.cli.main import app

runner = CliRunner()


def test_ingest_fx_command_exists() -> None:
    """测试汇率摄取命令存在."""
    result = runner.invoke(app, ["ingest", "market", "fx", "--help"])
    assert result.exit_code == 0


def test_ingest_commodity_command_exists() -> None:
    """测试商品摄取命令存在."""
    result = runner.invoke(app, ["ingest", "market", "commodity", "--help"])
    assert result.exit_code == 0
```

**Step 2: Run test to verify it fails**

```bash
pixi run -e dev pytest apps/port/tests/unit/cli/test_market_commands.py -v
```
Expected: FAIL

**Step 3: Write implementation**

在 `apps/port/src/ditto_port/cli/commands/ingest/market.py` 添加新命令：

```python
# 在文件末尾添加

@app.command("fx")
def fx(
    ctx: typer.Context,
    date: str = typer.Argument(..., help="交易日期 (YYYY-MM-DD)"),
    force: bool = typer.Option(False, "--force", "-f", help="强制重新摄取"),
) -> None:
    """摄取汇率日线数据."""
    return _fx_daily_impl(ctx, date, force)


_fx_daily_impl = create_daily_command("fx_daily", "摄取汇率日线数据")


@app.command("commodity")
def commodity(
    ctx: typer.Context,
    date: str = typer.Argument(..., help="交易日期 (YYYY-MM-DD)"),
    force: bool = typer.Option(False, "--force", "-f", help="强制重新摄取"),
) -> None:
    """摄取商品价格数据."""
    return _commodity_daily_impl(ctx, date, force)


_commodity_daily_impl = create_daily_command("commodity_daily", "摄取商品价格数据")
```

在 `apps/port/src/ditto_port/models/config.py` 添加数据集配置：

```python
# 在 INGESTION_SPECS 字典中添加

    "fx_daily": DatasetSpec(
        dataset="fx_daily",
        domain=Domain.MARKET,
        tier=TaskTier.T1_INCREMENTAL,
        description="汇率日线数据",
        source=Source.TUSHARE,
        update_frequency="daily",
        depends_on=[Dataset.CALENDAR],
        critical_fields=["instrument_id", "trade_date", "close"],
        task_name="ingest_fx_daily",
        priority=56,
    ),
    "commodity_daily": DatasetSpec(
        dataset="commodity_daily",
        domain=Domain.MARKET,
        tier=TaskTier.T1_INCREMENTAL,
        description="商品价格数据",
        source=Source.FRED,
        update_frequency="daily",
        depends_on=[Dataset.CALENDAR],
        critical_fields=["instrument_id", "trade_date", "close"],
        task_name="ingest_commodity_daily",
        priority=57,
    ),
```

**Step 4: Run test to verify it passes**

```bash
pixi run -e dev pytest apps/port/tests/unit/cli/test_market_commands.py -v
```
Expected: PASS

**Step 5: Commit**

```bash
git add apps/port/src/ditto_port/cli/commands/ingest/market.py apps/port/src/ditto_port/models/config.py apps/port/tests/unit/cli/test_market_commands.py
git commit -m "feat(port): 新增汇率/商品摄取 CLI 命令

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Phase 6: 完成验证 `[S]`

### Task 6.1: 运行完整验证

**Step 1: Run type check**

```bash
pixi run -e dev type
```
Expected: PASS

**Step 2: Run lint**

```bash
pixi run -e dev lint
```
Expected: PASS

**Step 3: Run tests**

```bash
pixi run -e dev test --fast
```
Expected: PASS

**Step 4: Run architecture check**

```bash
pixi run -e dev arch-check
```
Expected: PASS

**Step 5: Commit (if any fixes needed)**

```bash
git add -A
git commit -m "fix: 修复验证问题

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## 验收标准

### 功能验收

- [ ] `pixi run ingest market fx 2024-01-15` 成功摄取汇率数据
- [ ] `pixi run ingest market commodity 2024-01-15` 成功摄取商品数据
- [ ] 利率数据通过现有 `pixi run ingest macro indicators` 命令摄取
- [ ] VIX 指数通过现有 `pixi run ingest macro indicators --source fred` 命令摄取

### 质量验收

- [ ] 类型检查通过: `pixi run -e dev type`
- [ ] Lint 检查通过: `pixi run -e dev lint`
- [ ] 测试通过: `pixi run -e dev test`
- [ ] 架构检查通过: `pixi run -e dev arch-check`

### 文档验收

- [ ] 更新 [verification-plan-2025.md](../../verification-plan-2025.md) 添加新数据集验证步骤

---

## 后续扩展（不在本期范围）

- Phase 7: 有色金属/农产品（需引入 AKShare）
- Phase 8: ETF 持仓数据（需实现爬虫）
