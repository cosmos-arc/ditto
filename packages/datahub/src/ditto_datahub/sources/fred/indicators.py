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
FRED_INDICATORS: dict[str, FredIndicator] = {
    # === Economic ===
    "US_GDP_QOQ": FredIndicator(
        series_id="A191RL1Q225SBEA",
        code="US_GDP_QOQ",
        name="美国GDP环比",
        category="economic",
        frequency="quarterly",
        unit="%",
        description="Real Gross Domestic Product, Percent Change from Preceding Period",
        need_pit=True,
    ),
    # === Prices ===
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
    # === Employment ===
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
    # === Money Supply ===
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
