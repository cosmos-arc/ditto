"""FRED macro indicator metadata definitions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

# Type aliases for clarity
CategoryType = Literal[
    "economic",
    "prices",
    "money_supply",
    "employment",
    "credit",
    "survey",
    "interest_rate",
    "commodity",
    "vix",
    "dollar_index",
]
FrequencyType = Literal["daily", "monthly", "quarterly"]


@dataclass(frozen=True)
class FredIndicator:
    """
    FRED indicator metadata.

    Attributes:
        series_id: FRED Series ID (e.g., "UNRATE", "GDP").
        code: Unified indicator code (e.g., "US_UNRATE").
        name: Chinese name.
        category: Indicator category.
        frequency: Data frequency.
        unit: Unit of measurement.
        description: Description.
        need_pit: Whether PIT tracking is needed.

    """

    series_id: str
    code: str
    name: str
    category: CategoryType
    frequency: FrequencyType
    unit: str
    description: str
    need_pit: bool = False


# FRED indicator registry
#
# 注册纪律（#432，2026-10-04 核查）：
# - 死序列不注册：GOLDAMGBD228NLBM/SLVPRUSD（FRED 2022-01 官方公告移除
#   IBA/LBMA 定盘数据）与 VIX9D（序列页访问失败 + 前轮 404 记录；工具
#   访问错误不等同官方下架，恢复可读后再评估）。金银参考已由 Tushare
#   fx_daily 的 FXCM XAU/XAG bid 承担，与历史 LBMA 定盘是不同基准，
#   身份见 tushare/adapters/metal.py。
# - 代码与口径一致：注册拉取的是原始序列（level/index）时，代码/名称/
#   单位不得承诺同比。展示 YoY 须显式派生（同一 vintage 宇宙内当前值与
#   12 个月前值）或固定 FRED 官方变换 pc1 并锁定请求身份；不得把 pch
#   当同比，也不得对已变换序列重复变换。当前无 YoY 消费者，不预置派生。
# - need_pit 不等于无发布滞后：UNRATE 月度发布并回改、M2 季调且年度
#   基准重算可达数年，均需修订管理（need_pit=True）。
FRED_INDICATORS: dict[str, FredIndicator] = {
    # === Economic ===
    "US_GDP_QOQ": FredIndicator(
        series_id="A191RL1Q225SBEA",
        code="US_GDP_QOQ",
        name="美国GDP环比",
        category="economic",
        frequency="quarterly",
        unit="%",
        description=(
            "Real GDP, Percent Change from Preceding Period, "
            "Seasonally Adjusted Annual Rate"
        ),
        need_pit=True,
    ),
    # === Prices（原始序列为季调指数 level，非同比） ===
    "US_CPI_INDEX": FredIndicator(
        series_id="CPIAUCSL",
        code="US_CPI_INDEX",
        name="美国CPI(季调指数)",
        category="prices",
        frequency="monthly",
        unit="指数(1982-84=100)",
        description=(
            "CPI for All Urban Consumers: All Items, "
            "Seasonally Adjusted Index (level, not YoY)"
        ),
        need_pit=True,
    ),
    "US_CORE_CPI_INDEX": FredIndicator(
        series_id="CPILFESL",
        code="US_CORE_CPI_INDEX",
        name="美国核心CPI(季调指数)",
        category="prices",
        frequency="monthly",
        unit="指数(1982-84=100)",
        description=(
            "Core CPI (Excluding Food and Energy), "
            "Seasonally Adjusted Index (level, not YoY)"
        ),
        need_pit=True,
    ),
    "US_PCE_INDEX": FredIndicator(
        series_id="PCEPI",
        code="US_PCE_INDEX",
        name="美国PCE物价指数(季调)",
        category="prices",
        frequency="monthly",
        unit="指数(2017=100)",
        description=(
            "Personal Consumption Expenditures Price Index, "
            "Seasonally Adjusted (level, not YoY)"
        ),
        need_pit=True,
    ),
    "US_CORE_PCE_INDEX": FredIndicator(
        series_id="PCEPILFE",
        code="US_CORE_PCE_INDEX",
        name="美国核心PCE物价指数(季调)",
        category="prices",
        frequency="monthly",
        unit="指数(2017=100)",
        description=(
            "Core PCE (Excluding Food and Energy), Seasonally Adjusted (level, not YoY)"
        ),
        need_pit=True,
    ),
    # === Employment ===
    "US_UNRATE": FredIndicator(
        series_id="UNRATE",
        code="US_UNRATE",
        name="美国失业率",
        category="employment",
        frequency="monthly",
        unit="%",
        description="Civilian Unemployment Rate (monthly release, revised)",
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
    # === Money Supply（M2SL 为季调存量 level，非同比） ===
    "US_M2": FredIndicator(
        series_id="M2SL",
        code="US_M2",
        name="美国M2货币供应(季调)",
        category="money_supply",
        frequency="monthly",
        unit="十亿美元",
        description=(
            "M2 Money Stock, Seasonally Adjusted (level, not YoY; "
            "annual benchmark revisions can reach back years)"
        ),
        need_pit=True,
    ),
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
    # 贵金属（金银）不在此注册：GOLDAMGBD228NLBM/SLVPRUSD 已死序列（见
    # 文件头核查依据）；金银参考值由 Tushare fx_daily FXCM bid 提供（身份
    # 见 tushare/adapters/metal.py），与历史 LBMA 定盘分属不同基准。
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
    # === VIX (Market Domain) ===
    # VIX9D 不注册：序列页访问失败 + 前轮 404（见文件头核查依据）。
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
    # === Dollar Index (Market Domain) ===
    "US_DOLLAR_INDEX_BROAD": FredIndicator(
        series_id="DTWEXBGS",
        code="US_DOLLAR_INDEX_BROAD",
        name="美国贸易加权美元指数(广义)",
        category="dollar_index",
        frequency="daily",
        unit="指数",
        description="Trade Weighted U.S. Dollar Index: Broad, Goods and Services",
        need_pit=False,
    ),
}


def get_fred_indicator(code: str) -> FredIndicator | None:
    """
    Get FRED indicator metadata by code.

    Args:
        code: Unified indicator code (e.g., "US_UNRATE").

    Returns:
        FredIndicator if found, None otherwise.

    """
    return FRED_INDICATORS.get(code)


def list_fred_indicators(
    category: str | None = None,
    frequency: str | None = None,
) -> list[FredIndicator]:
    """
    List FRED indicators with optional filtering.

    Args:
        category: Filter by category (optional).
        frequency: Filter by frequency (optional).

    Returns:
        List of matching FredIndicator objects.

    """
    result = list(FRED_INDICATORS.values())
    if category:
        result = [i for i in result if i.category == category]
    if frequency:
        result = [i for i in result if i.frequency == frequency]
    return result


__all__ = [
    "FRED_INDICATORS",
    "FredIndicator",
    "get_fred_indicator",
    "list_fred_indicators",
]
