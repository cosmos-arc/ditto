"""FRED macro indicator metadata definitions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

# Type aliases for clarity
CategoryType = Literal[
    "economic", "prices", "money_supply", "employment", "credit", "survey"
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
