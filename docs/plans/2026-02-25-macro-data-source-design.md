# 宏观数据源统一设计文档

**日期**: 2026-02-25
**状态**: 设计完成，待实施
**前置文档**: [Macro 与 Market 域边界设计](2026-02-25-macro-and-market-domain-boundary-design.md)

---

## 1. 决策记录

| 日期 | 决策 | 理由 |
|------|------|------|
| 2026-02-25 | 中国宏观数据使用 Tushare | 本地数据源，覆盖完整 |
| 2026-02-25 | 美国宏观数据使用 FRED | 官方权威，免费完整 |
| 2026-02-25 | 先实现框架 + 基础指标 | 渐进式实施，降低风险 |
| 2026-02-25 | **直接 HTTP 对接 FRED API** | fredapi 返回 pandas，与项目 polars 架构不符 |
| 2026-02-25 | 限流机制：tenacity 重试 + 速率限制 | 保护 API 调用稳定性 |
| 2026-02-25 | 历史数据范围：2010-01-01 起 | 与行情数据对齐 |
| 2026-02-25 | 摄取模式：日期范围 + 增量更新 | 灵活支持回填和日常更新 |
| 2026-02-25 | **Tushare knowledge_date = 发布规律估算** | Tushare API 不提供发布日期，基于国家统计局/央行官方发布规律估算 |

---

## 2. 架构设计

### 2.1 数据源分工

| 地区 | 数据源 | 指标范围 |
|------|--------|---------|
| 中国 | Tushare | GDP、CPI、PPI、PMI、M2、社融等 |
| 美国 | FRED | GDP、CPI、PCE、就业、货币供应等 |

### 2.2 整体架构

```
┌─────────────────────────────────────────────────────────────────┐
│                        Macro 数据源层                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   ┌─────────────────────┐       ┌─────────────────────┐        │
│   │    TushareSource    │       │     FredSource      │        │
│   │    (中国宏观数据)    │       │    (美国宏观数据)    │        │
│   │                     │       │                     │        │
│   │  TushareClient      │       │  FredClient         │        │
│   │  (HTTP + JSON)      │       │  (HTTP + JSON)      │        │
│   │         ↓           │       │         ↓           │        │
│   │  MacroTushareAdapter│       │  MacroFredAdapter   │        │
│   │         ↓           │       │         ↓           │        │
│   └─────────┬───────────┘       └─────────┬───────────┘        │
│             │                             │                     │
│             ▼                             ▼                     │
│   ┌─────────────────────────────────────────────────────────┐  │
│   │        统一的 MACRO_INDICATOR_SOURCE_SCHEMA              │  │
│   │  (indicator_code, date, value, knowledge_date,          │  │
│   │   category, frequency, source, ...)                     │  │
│   └─────────────────────────────────────────────────────────┘  │
│                             │                                   │
│                             ▼                                   │
│                  ┌───────────────────┐                          │
│                  │   MacroService    │                          │
│                  │   (统一查询)       │                          │
│                  └───────────────────┘                          │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 3. 中国宏观数据（Tushare）

### 3.1 Tushare 宏观接口

| 接口名 | 指标 | 频率 | 参数格式 | 最低积分 |
|--------|------|------|---------|---------|
| `cn_gdp` | GDP | 季度 | `start_q='2020Q1'` | 5000 |
| `cn_cpi` | CPI | 月度 | `start_m='202001'` | 2000 |
| `cn_ppi` | PPI | 月度 | `start_m='202001'` | 2000 |
| `cn_pmi` | PMI | 月度 | `start_m='202001'` | 2000 |
| `cn_m` | M0/M1/M2 | 月度 | `start_m='202001'` | 2000 |
| `cn_shz` | 社会融资规模 | 月度 | `start_m='202001'` | 5000 |

### 3.2 中国宏观指标定义

```python
"""Tushare 中国宏观指标元数据定义。"""

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class TushareMacroIndicator:
    """Tushare 宏观指标元数据。"""

    api_name: str                    # Tushare API 名称（如 "cn_gdp"）
    code: str                        # 统一指标代码（如 "CN_GDP_QOQ"）
    name: str                        # 中文名称
    category: Literal["economic", "prices", "money_supply", "employment", "credit", "survey"]
    frequency: Literal["monthly", "quarterly"]
    value_field: str                 # 值字段名（如 "gdp", "nt_val"）
    unit: str                        # 单位
    description: str                 # 描述
    need_pit: bool = False           # 是否需要 PIT（数据修订追踪）
    date_field: str = "quarter"      # 日期字段名（quarter 或 month）
    date_format: str = "%YQ%m"       # 日期格式（"%YQ%m" 或 "%Y%m"）


# Tushare 中国宏观指标注册表
TUSHARE_MACRO_INDICATORS: dict[str, TushareMacroIndicator] = {
    # === P0: 首批实现 ===
    "CN_GDP_QOQ": TushareMacroIndicator(
        api_name="cn_gdp",
        code="CN_GDP_QOQ",
        name="中国GDP同比",
        category="economic",
        frequency="quarterly",
        value_field="gdp",
        date_field="quarter",
        date_format="%YQ%m",
        unit="亿元",
        description="国内生产总值（当季值）",
        need_pit=True,  # GDP 会修订
    ),
    "CN_CPI_YOY": TushareMacroIndicator(
        api_name="cn_cpi",
        code="CN_CPI_YOY",
        name="中国CPI同比",
        category="prices",
        frequency="monthly",
        value_field="nt_val",  # 同比值
        date_field="month",
        date_format="%Y%m",
        unit="%",
        description="全国居民消费价格指数同比",
        need_pit=False,
    ),
    "CN_PPI_YOY": TushareMacroIndicator(
        api_name="cn_ppi",
        code="CN_PPI_YOY",
        name="中国PPI同比",
        category="prices",
        frequency="monthly",
        value_field="ppi_yoy",
        date_field="month",
        date_format="%Y%m",
        unit="%",
        description="工业生产者出厂价格指数同比",
        need_pit=False,
    ),
    "CN_PMI_MFG": TushareMacroIndicator(
        api_name="cn_pmi",
        code="CN_PMI_MFG",
        name="中国制造业PMI",
        category="survey",
        frequency="monthly",
        value_field="pmi_mfg",  # 制造业PMI
        date_field="month",
        date_format="%Y%m",
        unit="指数",
        description="制造业采购经理指数",
        need_pit=False,
    ),

    # === P1: 后续扩展 ===
    "CN_M2_YOY": TushareMacroIndicator(
        api_name="cn_m",
        code="CN_M2_YOY",
        name="中国M2同比",
        category="money_supply",
        frequency="monthly",
        value_field="m2_yoy",
        date_field="month",
        date_format="%Y%m",
        unit="%",
        description="广义货币供应量M2同比",
        need_pit=False,
    ),
    "CN_M1_YOY": TushareMacroIndicator(
        api_name="cn_m",
        code="CN_M1_YOY",
        name="中国M1同比",
        category="money_supply",
        frequency="monthly",
        value_field="m1_yoy",
        date_field="month",
        date_format="%Y%m",
        unit="%",
        description="狭义货币供应量M1同比",
        need_pit=False,
    ),
    "CN_M0_YOY": TushareMacroIndicator(
        api_name="cn_m",
        code="CN_M0_YOY",
        name="中国M0同比",
        category="money_supply",
        frequency="monthly",
        value_field="m0_yoy",
        date_field="month",
        date_format="%Y%m",
        unit="%",
        description="流通中货币M0同比",
        need_pit=False,
    ),
    "CN_CREDIT_TS": TushareMacroIndicator(
        api_name="cn_shz",
        code="CN_CREDIT_TS",
        name="中国社会融资规模",
        category="credit",
        frequency="monthly",
        value_field="total_social_financing",
        date_field="month",
        date_format="%Y%m",
        unit="亿元",
        description="社会融资规模增量",
        need_pit=True,
    ),
}


def get_tushare_indicator(code: str) -> TushareMacroIndicator | None:
    """获取 Tushare 指标元数据。"""
    return TUSHARE_MACRO_INDICATORS.get(code)


def list_tushare_indicators(
    category: str | None = None,
    frequency: str | None = None,
) -> list[TushareMacroIndicator]:
    """列出符合条件的 Tushare 指标。"""
    result = list(TUSHARE_MACRO_INDICATORS.values())
    if category:
        result = [i for i in result if i.category == category]
    if frequency:
        result = [i for i in result if i.frequency == frequency]
    return result
```

### 3.3 Tushare 日期解析

Tushare 宏观数据的日期格式特殊，需要专门处理：

```python
"""Tushare 宏观数据日期解析。"""

import re
from datetime import date


def parse_tushare_quarter(quarter_str: str) -> date:
    """解析 Tushare 季度格式（如 "2024Q1"）为日期。

    转换规则：季度第一天作为日期
    - 2024Q1 -> 2024-01-01
    - 2024Q2 -> 2024-04-01
    - 2024Q3 -> 2024-07-01
    - 2024Q4 -> 2024-10-01
    """
    match = re.match(r"(\d{4})Q(\d)", quarter_str)
    if not match:
        raise ValueError(f"Invalid quarter format: {quarter_str}")

    year = int(match.group(1))
    quarter = int(match.group(2))

    quarter_start_month = {1: 1, 2: 4, 3: 7, 4: 10}
    return date(year, quarter_start_month[quarter], 1)


def parse_tushare_month(month_str: str) -> date:
    """解析 Tushare 月度格式（如 "202401"）为日期。

    转换规则：月份第一天作为日期
    - 202401 -> 2024-01-01
    """
    if len(month_str) != 6:
        raise ValueError(f"Invalid month format: {month_str}")

    year = int(month_str[:4])
    month = int(month_str[4:6])
    return date(year, month, 1)


def format_tushare_quarter(start_date: str, end_date: str) -> tuple[str, str]:
    """将日期范围转换为 Tushare 季度格式。

    Args:
        start_date: 开始日期（YYYY-MM-DD）
        end_date: 结束日期（YYYY-MM-DD）

    Returns:
        (start_q, end_q) 如 ("2010Q1", "2024Q4")
    """
    from datetime import datetime

    start = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d")

    def to_quarter(dt: datetime) -> str:
        quarter = (dt.month - 1) // 3 + 1
        return f"{dt.year}Q{quarter}"

    return to_quarter(start), to_quarter(end)


def format_tushare_month(start_date: str, end_date: str) -> tuple[str, str]:
    """将日期范围转换为 Tushare 月度格式。

    Args:
        start_date: 开始日期（YYYY-MM-DD）
        end_date: 结束日期（YYYY-MM-DD）

    Returns:
        (start_m, end_m) 如 ("201001", "202412")
    """
    from datetime import datetime

    start = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d")

    return start.strftime("%Y%m"), end.strftime("%Y%m")
```

### 3.4 MacroTushareAdapter 扩展设计

```python
"""Tushare 宏观指标适配器（扩展版）。"""

from __future__ import annotations

from datetime import date

import polars as pl
from ditto_infra.foundation import logger, traced

from ditto_datahub.sources.tushare.adapters.base import BaseTushareAdapter
from ditto_datahub.sources.tushare.processors.error_handler import (
    tushare_fetch_error_handler,
)
from ditto_datahub.sources.schemas.macro_schemas import MACRO_INDICATOR_SOURCE_SCHEMA

from .indicators import (
    TUSHARE_MACRO_INDICATORS,
    TushareMacroIndicator,
    parse_tushare_quarter,
    parse_tushare_month,
    format_tushare_quarter,
    format_tushare_month,
)


class MacroTushareAdapter(BaseTushareAdapter):
    """Tushare 宏观指标适配器。

    将 Tushare 宏观数据转换为统一的 MACRO_INDICATOR_SOURCE_SCHEMA。
    """

    @traced("source.tushare.fetch_macro_indicators")
    def fetch_indicators(
        self,
        codes: list[str],
        start_date: str,
        end_date: str,
    ) -> pl.DataFrame:
        """获取多个宏观指标数据。

        Args:
            codes: 指标代码列表（如 ["CN_GDP_QOQ", "CN_CPI_YOY"]）
            start_date: 开始日期（YYYY-MM-DD）
            end_date: 结束日期（YYYY-MM-DD）

        Returns:
            符合 MACRO_INDICATOR_SOURCE_SCHEMA 的 DataFrame
        """
        frames: list[pl.DataFrame] = []

        for code in codes:
            indicator = TUSHARE_MACRO_INDICATORS.get(code)
            if not indicator:
                logger.warning(f"未知的指标代码: {code}")
                continue

            df = self._fetch_single_indicator(indicator, start_date, end_date)
            if not df.is_empty():
                frames.append(df)

        if not frames:
            return _empty_macro_dataframe()

        return pl.concat(frames)

    def _fetch_single_indicator(
        self,
        indicator: TushareMacroIndicator,
        start_date: str,
        end_date: str,
    ) -> pl.DataFrame:
        """获取单个指标数据并标准化。"""
        logger.info(
            "Fetching Tushare macro indicator",
            event="tushare_macro_fetch_start",
            api_name=indicator.api_name,
            code=indicator.code,
        )

        # 根据频率转换日期格式
        if indicator.frequency == "quarterly":
            start_param, end_param = format_tushare_quarter(start_date, end_date)
            date_param_name = "start_q"
            end_param_name = "end_q"
        else:  # monthly
            start_param, end_param = format_tushare_month(start_date, end_date)
            date_param_name = "start_m"
            end_param_name = "end_m"

        with tushare_fetch_error_handler("macro_indicators", indicator.api_name):
            response = self._client.query(
                api_name=indicator.api_name,
                fields=f"{indicator.date_field},{indicator.value_field}",
                **{date_param_name: start_param, end_param_name: end_param},
            )

            if response.is_empty():
                return _empty_macro_dataframe()

            # 解析日期
            if indicator.frequency == "quarterly":
                response = response.with_columns(
                    pl.col(indicator.date_field)
                    .map_elements(parse_tushare_quarter, return_dtype=pl.Date)
                    .alias("date")
                )
            else:  # monthly
                response = response.with_columns(
                    pl.col(indicator.date_field)
                    .map_elements(parse_tushare_month, return_dtype=pl.Date)
                    .alias("date")
                )

            # 标准化为 MACRO_INDICATOR_SOURCE_SCHEMA
            # 注意: Tushare 不提供发布日期，基于官方发布规律估算 knowledge_date
            result = response.with_columns(
                pl.lit(indicator.code).alias("indicator_code"),
                pl.lit(indicator.name).alias("indicator_name"),
                pl.lit(indicator.category).alias("category"),
                pl.lit(indicator.frequency).alias("frequency"),
                pl.lit(indicator.need_pit).alias("need_pit"),
                pl.col("date"),
                pl.col(indicator.value_field).cast(pl.Float64).alias("value"),
                # 基于官方发布规律估算 knowledge_date
                pl.col("date").map_elements(
                    lambda d: estimate_knowledge_date(d, indicator.code),
                    return_dtype=pl.Date,
                ).alias("knowledge_date"),
                pl.lit("tushare").alias("source"),
                pl.lit(indicator.unit).alias("unit"),
                pl.lit(indicator.description).alias("description"),
            ).select(list(MACRO_INDICATOR_SOURCE_SCHEMA.schema.keys()))

            logger.info(
                "Fetched Tushare macro indicator",
                event="tushare_macro_fetch_complete",
                code=indicator.code,
                row_count=len(result),
            )

            return result


def _empty_macro_dataframe() -> pl.DataFrame:
    """返回空的宏观指标 DataFrame。"""
    return pl.DataFrame(schema=MACRO_INDICATOR_SOURCE_SCHEMA.schema)
```

### 3.5 目录结构（扩展 Tushare）

```
packages/datahub/src/ditto_datahub/sources/tushare/
├── adapters/
│   ├── macro.py                    # 扩展现有实现
│   └── ...
├── processors/
│   └── ...
├── indicators/                     # 新增目录
│   ├── __init__.py
│   └── macro_indicators.py         # TUSHARE_MACRO_INDICATORS 定义
└── utils/                          # 新增目录
    ├── __init__.py
    └── date_parser.py              # 日期解析工具
```

---

## 4. 美国宏观数据（FRED）

### 4.1 FRED API 端点

| 端点 | 用途 |
|------|------|
| `GET /fred/series/observations` | 获取指标数据序列 |
| `GET /fred/series` | 获取指标元数据 |

### 4.2 请求示例

```
GET https://api.stlouisfed.org/fred/series/observations
    ?series_id=UNRATE
    &api_key=xxxxxxxx
    &observation_start=2010-01-01
    &observation_end=2024-12-31
    &file_type=json
```

### 4.3 响应结构

```json
{
  "realtime_start": "2024-01-01",
  "realtime_end": "2024-12-31",
  "series_id": "UNRATE",
  "observations": [
    {"realtime_start": "2024-01-01", "realtime_end": "2024-12-31", "date": "2024-01-01", "value": "3.7"},
    {"realtime_start": "2024-01-01", "realtime_end": "2024-12-31", "date": "2024-02-01", "value": "3.9"}
  ]
}
```

### 4.4 FRED 指标定义

```python
"""FRED 宏观指标元数据定义。"""

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class FredIndicator:
    """FRED 指标元数据。"""

    series_id: str                    # FRED Series ID（如 "UNRATE"）
    code: str                         # 统一指标代码（如 "US_UNRATE"）
    name: str                         # 中文名称
    category: Literal["economic", "prices", "money_supply", "employment", "credit", "survey"]
    frequency: Literal["daily", "monthly", "quarterly"]
    unit: str                         # 单位
    description: str                  # 描述
    need_pit: bool = False            # 是否需要 PIT


# FRED 指标注册表
FRED_INDICATORS: dict[str, FredIndicator] = {
    # === P0: 首批实现 ===
    "US_GDP_QOQ": FredIndicator(
        series_id="A191RL1Q225SBEA",
        code="US_GDP_QOQ",
        name="美国GDP实际同比",
        category="economic",
        frequency="quarterly",
        unit="%",
        description="Real Gross Domestic Product, Percent Change from Preceding Period",
        need_pit=True,
    ),
    "US_CPI_YOY": FredIndicator(
        series_id="CPIAUCSL",
        code="US_CPI_YOY",
        name="美国CPI同比",
        category="prices",
        frequency="monthly",
        unit="指数",
        description="Consumer Price Index for All Urban Consumers: All Items",
        need_pit=True,
    ),
    "US_UNRATE": FredIndicator(
        series_id="UNRATE",
        code="US_UNRATE",
        name="美国失业率",
        category="employment",
        frequency="monthly",
        unit="%",
        description="Civilian Unemployment Rate",
        need_pit=False,
    ),

    # === P1: 后续扩展 ===
    "US_CPI_CORE_YOY": FredIndicator(
        series_id="CPILFESL",
        code="US_CPI_CORE_YOY",
        name="美国核心CPI同比",
        category="prices",
        frequency="monthly",
        unit="指数",
        description="Core CPI (Excluding Food and Energy)",
        need_pit=True,
    ),
    "US_PCE_YOY": FredIndicator(
        series_id="PCEPI",
        code="US_PCE_YOY",
        name="美国PCE同比",
        category="prices",
        frequency="monthly",
        unit="指数",
        description="Personal Consumption Expenditures Price Index",
        need_pit=True,
    ),
    "US_PCE_CORE_YOY": FredIndicator(
        series_id="PCEPILFE",
        code="US_PCE_CORE_YOY",
        name="美国核心PCE同比",
        category="prices",
        frequency="monthly",
        unit="指数",
        description="Core PCE (Excluding Food and Energy)",
        need_pit=True,
    ),
    "US_PAYEMS": FredIndicator(
        series_id="PAYEMS",
        code="US_PAYEMS",
        name="美国非农就业",
        category="employment",
        frequency="monthly",
        unit="千人",
        description="Nonfarm Employment",
        need_pit=True,
    ),
    "US_M2_YOY": FredIndicator(
        series_id="M2SL",
        code="US_M2_YOY",
        name="美国M2同比",
        category="money_supply",
        frequency="monthly",
        unit="十亿美元",
        description="M2 Money Stock",
        need_pit=False,
    ),
}
```

### 4.5 FredClient 设计

```python
"""FRED API 客户端封装。"""

from __future__ import annotations

import os
from typing import Any

import httpx
import polars as pl
from tenacity import retry, stop_after_attempt, wait_exponential

from ditto_datahub.sources.base import (
    SourceAuthenticationError,
    SourceConfigurationError,
    SourceFetchError,
)

FRED_API_BASE_URL = "https://api.stlouisfed.org/fred"


class FredClient:
    """FRED API 客户端。

    直接通过 HTTP 对接 FRED API，返回 polars DataFrame。
    """

    def __init__(self, api_key: str | None = None) -> None:
        """初始化 FRED 客户端。

        Args:
            api_key: FRED API Key。如果为 None，从环境变量 FRED_API_KEY 读取。

        Raises:
            SourceConfigurationError: API Key 未配置。
        """
        self._api_key = api_key or os.environ.get("FRED_API_KEY")
        if not self._api_key:
            raise SourceConfigurationError(
                "FRED API Key 未配置",
                env_var="FRED_API_KEY",
            )

        self._client = httpx.Client(base_url=FRED_API_BASE_URL, timeout=30.0)

    def close(self) -> None:
        """关闭 HTTP 客户端。"""
        self._client.close()

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    def get_series_observations(
        self,
        series_id: str,
        observation_start: str,
        observation_end: str,
    ) -> pl.DataFrame:
        """获取指标数据序列。

        Args:
            series_id: FRED 指标 ID（如 "UNRATE"）
            observation_start: 开始日期（YYYY-MM-DD）
            observation_end: 结束日期（YYYY-MM-DD）

        Returns:
            包含列 [date, value, realtime_start, realtime_end] 的 DataFrame
        """
        params: dict[str, Any] = {
            "series_id": series_id,
            "api_key": self._api_key,
            "observation_start": observation_start,
            "observation_end": observation_end,
            "file_type": "json",
        }

        try:
            response = self._client.get("/series/observations", params=params)
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                raise SourceAuthenticationError(
                    "FRED API 认证失败",
                    source="fred",
                ) from e
            raise SourceFetchError(
                f"FRED API 请求失败: {e.response.status_code}",
                source="fred",
                dataset=series_id,
                original_error=str(e),
            ) from e
        except httpx.RequestError as e:
            raise SourceFetchError(
                "FRED API 网络错误",
                source="fred",
                dataset=series_id,
                original_error=str(e),
            ) from e

        data = response.json()
        observations = data.get("observations", [])

        if not observations:
            return pl.DataFrame(schema={
                "date": pl.Date,
                "value": pl.Float64,
                "realtime_start": pl.Date,
                "realtime_end": pl.Date,
            })

        df = pl.DataFrame(observations)
        return df.with_columns(
            pl.col("date").str.to_date(strict=False),
            pl.col("value").cast(pl.Float64, strict=False),
            pl.col("realtime_start").str.to_date(strict=False),
            pl.col("realtime_end").str.to_date(strict=False),
        )
```

### 4.6 FRED 目录结构

```
packages/datahub/src/ditto_datahub/sources/fred/
├── __init__.py
├── client.py              # FredClient: HTTP 请求封装
├── fred_source.py         # FredSource: DataSource 实现
├── adapters/
│   ├── __init__.py
│   └── macro.py           # MacroFredAdapter: 宏观指标适配器
└── indicators.py          # FRED_INDICATORS: 指标元数据定义
```

---

## 5. CLI 命令设计

### 5.1 统一命令接口

```bash
# 摄取所有宏观指标（中国 + 美国）
pixi run ingest macro --start 2010-01-01 --end 2024-12-31

# 只摄取中国宏观数据
pixi run ingest macro cn --start 2010-01-01 --end 2024-12-31

# 只摄取美国宏观数据（FRED）
pixi run ingest macro fred --start 2010-01-01 --end 2024-12-31

# 指定指标摄取
pixi run ingest macro cn --indicators CN_GDP_QOY,CN_CPI_YOY --start 2020-01-01

# 增量更新
pixi run ingest macro --incremental

# 强制重新摄取
pixi run ingest macro --start 2024-01-01 --end 2024-12-31 --force
```

### 5.2 CLI 目录结构

```
apps/port/src/ditto_port/cli/commands/ingest/
├── macro.py               # 宏观摄取入口
├── macro_cn.py            # 中国宏观数据摄取
└── macro_fred.py          # FRED 宏观数据摄取
```

---

## 6. 配置

### 6.1 环境变量

```bash
# config/development/data_source.env

# Tushare（中国数据）
TUSHARE_TOKEN=your_tushare_token

# FRED（美国数据）
FRED_API_KEY=your_fred_api_key
```

### 6.2 依赖

```toml
# 无需新增依赖，使用项目现有的：
# - httpx (HTTP 客户端)
# - tenacity (重试)
# - polars (DataFrame)
```

---

## 7. 测试策略

### 7.1 测试文件结构

```
packages/datahub/tests/unit/sources/
├── tushare/
│   └── test_macro_adapter_unit.py    # Tushare 宏观适配器测试
└── fred/
    ├── test_client_unit.py           # FredClient 单元测试
    ├── test_indicators_unit.py       # FRED 指标元数据测试
    └── test_macro_adapter_unit.py    # MacroFredAdapter 单元测试
```

### 7.2 核心测试用例

**Tushare 宏观适配器**:
- `test_fetch_single_indicator_quarterly()` - 季度数据（GDP）
- `test_fetch_single_indicator_monthly()` - 月度数据（CPI）
- `test_parse_tushare_quarter()` - 季度格式解析
- `test_parse_tushare_month()` - 月度格式解析
- `test_schema_normalization()` - Schema 标准化

**FRED 宏观适配器**:
- `test_get_series_observations_success()`
- `test_get_series_observations_empty_response()`
- `test_get_series_observations_auth_error()`
- `test_fetch_multiple_indicators()`

---

## 8. 实施计划

### Phase 1：FRED 框架搭建

- [ ] 创建 `sources/fred/` 目录结构
- [ ] 实现 `FredClient`（HTTP + 重试）
- [ ] 实现 `FRED_INDICATORS`（P0 指标定义）
- [ ] 编写 `FredClient` 单元测试

### Phase 2：FRED 适配器实现

- [ ] 实现 `MacroFredAdapter`
- [ ] 实现 Schema 标准化
- [ ] 编写适配器单元测试
- [ ] 集成到现有摄取流程

### Phase 3：Tushare 宏观扩展

- [ ] 创建 `indicators/macro_indicators.py`
- [ ] 实现 `TUSHARE_MACRO_INDICATORS` 定义
- [ ] 实现日期解析工具（季度/月度格式）
- [ ] 扩展 `MacroTushareAdapter`
- [ ] 编写单元测试

### Phase 4：CLI 集成

- [ ] 实现 `ingest macro` 统一入口
- [ ] 实现 `ingest macro cn` 子命令
- [ ] 实现 `ingest macro fred` 子命令
- [ ] 支持日期范围 + 增量更新模式

### Phase 5：扩展指标

- [ ] 添加 P1 优先级指标
- [ ] API 端点更新

---

## 9. 指标优先级汇总

### P0（首批实现）

| 地区 | 指标代码 | 指标名称 | 数据源 |
|------|---------|---------|--------|
| 中国 | CN_GDP_QOQ | 中国GDP同比 | Tushare |
| 中国 | CN_CPI_YOY | 中国CPI同比 | Tushare |
| 中国 | CN_PPI_YOY | 中国PPI同比 | Tushare |
| 中国 | CN_PMI_MFG | 中国制造业PMI | Tushare |
| 美国 | US_GDP_QOQ | 美国GDP实际同比 | FRED |
| 美国 | US_CPI_YOY | 美国CPI同比 | FRED |
| 美国 | US_UNRATE | 美国失业率 | FRED |

### P1（后续扩展）

| 地区 | 指标代码 | 指标名称 | 数据源 |
|------|---------|---------|--------|
| 中国 | CN_M2_YOY | 中国M2同比 | Tushare |
| 中国 | CN_M1_YOY | 中国M1同比 | Tushare |
| 中国 | CN_CREDIT_TS | 中国社会融资规模 | Tushare |
| 美国 | US_CPI_CORE_YOY | 美国核心CPI同比 | FRED |
| 美国 | US_PCE_YOY | 美国PCE同比 | FRED |
| 美国 | US_PCE_CORE_YOY | 美国核心PCE同比 | FRED |
| 美国 | US_PAYEMS | 美国非农就业 | FRED |
| 美国 | US_M2_YOY | 美国M2同比 | FRED |

---

## 10. PIT（Point-in-Time）设计

### 10.1 PIT 背景

宏观数据经常会被修订（revision），例如：
- **GDP**：初值、修正值、终值
- **CPI/PPI**：季节调整因子的更新
- **就业数据**：后续月份的修正

**PIT 查询的意义**：在回测时，需要知道"某个日期时，当时已知的数据是什么"，而不是"最新发布的数据"。

### 10.2 ALFRED vs FRED

| 特性 | FRED | ALFRED |
|------|------|--------|
| **数据** | 最新值 | 历史所有版本 |
| **API** | 同一端点 | 同一端点，额外参数 |
| **用途** | 当前分析 | 回测、历史研究 |
| **响应** | 每个日期一条 | 每个日期可能多条（不同版本） |

**ALFRED API 示例**：
```
GET /fred/series/observations
    ?series_id=GDP
    &api_key=xxx
    &observation_start=2020-01-01
    &observation_end=2024-12-31
    &realtime_start=2020-01-01    # PIT 查询：只返回 2020-01-01 时已知的数据
    &realtime_end=2020-12-31
```

### 10.3 PIT 数据模型

**响应结构（ALFRED）**：
```json
{
  "observations": [
    {
      "date": "2024-01-01",           // 数据日期
      "value": "3.2",                  // 数据值
      "realtime_start": "2024-02-28", // 此版本首次发布的日期
      "realtime_end": "2024-03-28"    // 此版本被新版本替换的日期
    },
    {
      "date": "2024-01-01",           // 同一数据日期
      "value": "3.1",                  // 修正后的值
      "realtime_start": "2024-03-28", // 修正版发布日期
      "realtime_end": "9999-12-31"    // 当前版本（未过期）
    }
  ]
}
```

### 10.4 PIT 存储策略

**方案 A：全量 PIT 存储（推荐）**

存储所有版本，通过 `knowledge_date` 和 `effective_to` 管理有效期：

```sql
-- macro_indicator_data 表
CREATE TABLE macro_indicator_data (
    indicator_id INTEGER NOT NULL,
    date DATE NOT NULL,              -- 数据日期
    value REAL,                       -- 数据值
    knowledge_date DATE NOT NULL,    -- 数据发布日期（PIT 关键字段）
    effective_from DATE NOT NULL,    -- 有效期起始（= knowledge_date）
    effective_to DATE,               -- 有效期结束（下一版本发布日期，NULL 表示当前版本）
    PRIMARY KEY (indicator_id, date, effective_from)
);
```

**存储示例**：

| indicator_id | date | value | knowledge_date | effective_from | effective_to |
|-------------|------|-------|----------------|----------------|--------------|
| US_GDP_QOQ | 2024-Q1 | 3.2% | 2024-04-28 | 2024-04-28 | 2024-05-28 |
| US_GDP_QOQ | 2024-Q1 | 3.1% | 2024-05-28 | 2024-05-28 | 2024-06-28 |
| US_GDP_QOQ | 2024-Q1 | 3.0% | 2024-06-28 | 2024-06-28 | NULL |

**方案 B：仅存储最新值 + 变更日志**

当前架构已支持的简化方案，适合不需要精确 PIT 回测的场景。

### 10.5 PIT 查询 API

```python
class MacroService:
    def get_indicators(
        self,
        query: MacroQuery,
    ) -> pl.DataFrame:
        """
        查询宏观指标数据。

        Args:
            query: MacroQuery 查询对象
                - indicators: 指标代码列表
                - start/end: 数据日期范围
                - asof: PIT 查询日期（只返回此日期时已知的数据）
        """

    def get_indicator_revisions(
        self,
        indicator_code: str,
        date: str,
    ) -> pl.DataFrame:
        """
        获取某个数据点的所有历史修订版本。

        Returns:
            包含所有版本的 DataFrame，按 knowledge_date 排序
        """
```

**PIT 查询示例**：

```python
# 查询 2024-03-01 时已知的 2024-Q1 GDP 数据
macro_service.get_indicators(
    MacroQuery(
        indicators=["US_GDP_QOQ"],
        start="2024-01-01",
        end="2024-03-31",
        asof="2024-03-01",  # PIT 查询：只返回 3月1日前发布的数据
    )
)
# 结果：返回 2024-Q1 GDP 的初值（如果 3月1日已发布）
```

### 10.6 FredClient PIT 支持

```python
class FredClient:
    def get_series_observations(
        self,
        series_id: str,
        observation_start: str,
        observation_end: str,
        realtime_start: str | None = None,  # PIT 参数
        realtime_end: str | None = None,    # PIT 参数
    ) -> pl.DataFrame:
        """
        获取指标数据序列。

        PIT 模式：
        - 不指定 realtime_*: 返回最新值（FRED 模式）
        - 指定 realtime_*: 返回指定时间范围内发布的版本（ALFRED 模式）
        """
        params: dict[str, Any] = {
            "series_id": series_id,
            "api_key": self._api_key,
            "observation_start": observation_start,
            "observation_end": observation_end,
            "file_type": "json",
        }

        # PIT 参数
        if realtime_start:
            params["realtime_start"] = realtime_start
        if realtime_end:
            params["realtime_end"] = realtime_end

        # ...
```

### 10.7 Tushare PIT 考量

**Tushare 宏观数据 API 调研结论**（2026-02-25）：

经查阅 Tushare Pro 官方文档，确认以下 API 返回字段：

| API | 返回字段 | 发布日期字段 |
|-----|---------|-------------|
| `cn_gdp` | quarter, gdp, gdp_yoy, pi, pi_yoy, si, si_yoy, ti, ti_yoy | **无** |
| `cn_cpi` | month, nt_val, nt_yoy, nt_mom, nt_accu, town_*, cnt_* | **无** |
| `cn_ppi` | month, ppi_yoy, ppi_mp_yoy, ..., ppi_mom, ..., ppi_accu | **无** |
| `cn_m` | month, m0, m0_yoy, m0_mom, m1, m1_yoy, m1_mom, m2, m2_yoy, m2_mom | **无** |
| `cn_pmi` | month, pmi_mfg, ... | **无** |
| `cn_shz` | month, total_social_financing, ... | **无** |

**结论**：**Tushare 宏观数据 API 不提供发布日期（publish_date/announce_date）字段**，只返回数据日期（quarter/month）和数值字段。

#### 10.7.1 中国宏观数据官方发布规律

根据国家统计局和央行的官方发布制度，中国宏观数据有明确的发布时间规律：

| 指标类型 | 发布机构 | 发布时间 | 示例 |
|---------|---------|---------|------|
| **GDP（季度）** | 国家统计局 | **季后15日左右** | Q1数据→4月15日，Q2→7月15日，Q3→10月15日，Q4→次年1月17日 |
| **CPI/PPI** | 国家统计局 | **次月9日**（9:30，节假日顺延） | 1月CPI→2月9日 |
| **PMI** | 国家统计局 | **次月1日** | 1月PMI→2月1日 |
| **M2/社融/信贷** | 央行 | **次月11-15日**（通常11-14日傍晚） | 1月M2→2月11-14日 |

**数据来源**：
- [国家统计局主要统计信息发布日程表](https://www.stats.gov.cn/sj/fbrc/bnxxfb/)
- [季度GDP核算和数据发布制度](https://www.stats.gov.cn/zs/tjws/zytjzbqs/gnsczz/)

#### 10.7.2 knowledge_date 估算策略

**基于官方发布规律的估算函数**：

```python
from datetime import date
from calendar import monthrange


def estimate_knowledge_date(data_date: date, indicator_code: str) -> date:
    """基于官方发布规律估算 knowledge_date。

    根据国家统计局和央行的官方发布惯例，估算数据实际发布的日期。

    Args:
        data_date: 数据日期（如 2024-03-01 表示 2024年3月或2024年Q1）
        indicator_code: 指标代码（如 "CN_GDP_QOQ", "CN_CPI_YOY"）

    Returns:
        估算的发布日期（knowledge_date）
    """
    # GDP：季度数据，季后15日发布
    if indicator_code.startswith("CN_GDP"):
        return _estimate_gdp_release_date(data_date)

    # CPI/PPI：次月9日发布
    if indicator_code.startswith("CN_CPI") or indicator_code.startswith("CN_PPI"):
        return _next_month_day(data_date, day=9)

    # PMI：次月1日发布
    if indicator_code.startswith("CN_PMI"):
        return _next_month_day(data_date, day=1)

    # M0/M1/M2/社融：次月13日发布（取11-15日中间值）
    if indicator_code.startswith("CN_M") or indicator_code.startswith("CN_CREDIT"):
        return _next_month_day(data_date, day=13)

    # 默认：次月15日
    return _next_month_day(data_date, day=15)


def _estimate_gdp_release_date(data_date: date) -> date:
    """估算季度GDP的发布日期。

    发布规律：季后15日左右
    - Q1 (3月结束) → 4月15日
    - Q2 (6月结束) → 7月15日
    - Q3 (9月结束) → 10月15日
    - Q4 (12月结束) → 次年1月17日（年度核算发布会）
    """
    quarter = (data_date.month - 1) // 3 + 1
    quarter_end_month = quarter * 3  # 3, 6, 9, 12

    if quarter == 4:
        # Q4: 次年1月17日（年度国民经济运行情况发布会）
        return date(data_date.year + 1, 1, 17)
    else:
        # Q1-Q3: 季后次月15日
        release_month = quarter_end_month + 1  # 4, 7, 10
        return date(data_date.year, release_month, 15)


def _next_month_day(data_date: date, day: int) -> date:
    """计算次月的指定日期。

    Args:
        data_date: 数据日期
        day: 目标日期（如 9, 13, 15）

    Returns:
        次月的指定日期
    """
    year = data_date.year
    month = data_date.month + 1

    if month > 12:
        month = 1
        year += 1

    # 确保日期有效（如 2月31日 → 2月28日）
    _, max_day = monthrange(year, month)
    actual_day = min(day, max_day)

    return date(year, month, actual_day)
```

**估算示例**：

| 指标 | 数据日期 | 估算 knowledge_date | 说明 |
|------|---------|-------------------|------|
| CN_GDP_QOQ | 2024-03-01 (Q1) | 2024-04-15 | Q1季后15日 |
| CN_GDP_QOQ | 2024-12-01 (Q4) | 2025-01-17 | 年度发布会 |
| CN_CPI_YOY | 2024-01-01 | 2024-02-09 | 次月9日 |
| CN_PMI_MFG | 2024-01-01 | 2024-02-01 | 次月1日 |
| CN_M2_YOY | 2024-01-01 | 2024-02-13 | 次月13日 |

#### 10.7.3 指标元数据扩展

为支持 knowledge_date 估算，需要在指标定义中添加 `release_day` 字段：

```python
@dataclass(frozen=True)
class TushareMacroIndicator:
    """Tushare 宏观指标元数据。"""
    # ... 原有字段 ...

    # 发布日期估算参数
    release_type: Literal["next_month", "quarter_end"] = "next_month"
    release_day: int = 15  # 发布日（next_month 模式）或季后天数（quarter_end 模式）


# 更新指标定义
TUSHARE_MACRO_INDICATORS: dict[str, TushareMacroIndicator] = {
    "CN_GDP_QOQ": TushareMacroIndicator(
        # ...
        release_type="quarter_end",
        release_day=15,  # 季后15日（Q4为次年1月17日）
    ),
    "CN_CPI_YOY": TushareMacroIndicator(
        # ...
        release_type="next_month",
        release_day=9,  # 次月9日
    ),
    "CN_PMI_MFG": TushareMacroIndicator(
        # ...
        release_type="next_month",
        release_day=1,  # 次月1日
    ),
    "CN_M2_YOY": TushareMacroIndicator(
        # ...
        release_type="next_month",
        release_day=13,  # 次月13日
    ),
}
```

#### 10.7.4 适配器集成

**knowledge_date 确定策略**（优化版）：

```python
from datetime import date


def determine_knowledge_date(
    data_date: date,
    indicator_code: str,
    ingestion_date: date,
    existing_knowledge_date: date | None = None,
) -> date:
    """确定最终的 knowledge_date。

    策略：
    1. 如果已存在 knowledge_date，保留原值（首次获取的时间最准确）
    2. 如果获取时间 < 估算发布时间：使用获取时间（数据不可能在发布前获取）
    3. 如果获取时间 >= 估算发布时间：使用估算发布时间

    Args:
        data_date: 数据日期
        indicator_code: 指标代码
        ingestion_date: 当前获取时间
        existing_knowledge_date: 已存在的 knowledge_date（如果有）

    Returns:
        最终的 knowledge_date
    """
    # 1. 如果已存在，保留原值
    if existing_knowledge_date is not None:
        return existing_knowledge_date

    # 2. 估算的发布时间
    estimated_release = estimate_knowledge_date(data_date, indicator_code)

    # 3. 比较获取时间和估算发布时间
    if ingestion_date < estimated_release:
        # 获取时间早于估算发布时间：使用获取时间
        # 这表示数据可能在官方发布前就已在 Tushare 更新
        return ingestion_date
    else:
        # 获取时间晚于或等于估算发布时间：使用估算发布时间
        return estimated_release
```

**存储层集成**：

```python
class MacroIndicatorWriter:
    """宏观指标数据写入器。"""

    def upsert_indicators(
        self,
        df: pl.DataFrame,
        ingestion_date: date,
    ) -> None:
        """写入宏观指标数据，保留已有的 knowledge_date。"""
        for row in df.iter_rows(named=True):
            data_date = row["date"]
            indicator_code = row["indicator_code"]

            # 查询是否已存在
            existing = self._find_existing(indicator_code, data_date)
            existing_knowledge_date = existing["knowledge_date"] if existing else None

            # 确定 knowledge_date
            knowledge_date = determine_knowledge_date(
                data_date=data_date,
                indicator_code=indicator_code,
                ingestion_date=ingestion_date,
                existing_knowledge_date=existing_knowledge_date,
            )

            # 写入数据
            self._upsert_row(
                indicator_code=indicator_code,
                data_date=data_date,
                value=row["value"],
                knowledge_date=knowledge_date,
            )
```

**示例场景**：

| 场景 | 数据日期 | 估算发布 | 获取时间 | 已存在 | 最终 knowledge_date |
|------|---------|---------|---------|--------|-------------------|
| 首次获取（早于发布） | 2024-01-01 | 2024-02-09 | 2024-02-05 | 无 | **2024-02-05** |
| 首次获取（晚于发布） | 2024-01-01 | 2024-02-09 | 2024-02-15 | 无 | **2024-02-09** |
| 重复获取 | 2024-01-01 | 2024-02-09 | 2024-03-01 | 2024-02-05 | **2024-02-05**（保留） |
| 数据修订后重取 | 2024-01-01 | 2024-02-09 | 2024-03-15 | 2024-02-05 | **2024-02-05**（保留首次） |

#### 10.7.5 估算的局限性与后续优化

**局限性**：
1. 估算基于"标准发布规律"，未考虑节假日顺延
2. 历史数据的发布日期可能与当前规律不同
3. 无法获取实际发布日期的精确记录

**后续优化方向**：
1. **维护发布日历表**：记录每年的实际发布日期
2. **节假日调整**：集成中国节假日日历，处理顺延情况
3. **数据源扩展**：如果 Tushare 后续提供发布日期字段，直接使用

**与 FRED 的对比**：

| 维度 | FRED/ALFRED | Tushare（估算） |
|------|-------------|----------------|
| **发布日期来源** | API 直接提供 | 基于官方规律估算 |
| **精确度** | 精确到日 | ±1-2天（节假日影响） |
| **历史版本** | 完整记录 | 仅当前值 |
| **适用场景** | 精确 PIT 回测 | 近似 PIT 分析 |

### 10.8 PIT 实施优先级

| 优先级 | 任务 | 说明 |
|--------|------|------|
| P0 | 基础 PIT 支持 | 存储 knowledge_date，支持 asof 查询 |
| P1 | ALFRED 全量存储 | 获取并存储所有历史版本 |
| P1 | Tushare 快照存储 | 每次摄取记录快照 |
| P2 | PIT 变更检测 | 自动检测数据修订并记录 |

---

## 11. 参考资料

- [Tushare Pro 宏观数据接口](https://tushare.pro/document/2?doc_id=257)
- [FRED API 文档](https://fred.stlouisfed.org/docs/api/fred/)
- [FRED Series Observations Endpoint](https://fred.stlouisfed.org/docs/api/fred/series_observations.html)
- [FRED API Key 申请](https://fred.stlouisfed.org/docs/api/api_key.html)
