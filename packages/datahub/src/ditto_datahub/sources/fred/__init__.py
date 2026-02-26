"""FRED (Federal Reserve Economic Data) data source."""

from __future__ import annotations

from ditto_datahub.sources.fred.adapters.macro import MacroFredAdapter
from ditto_datahub.sources.fred.client import FredClient
from ditto_datahub.sources.fred.fred_source import ALL_FRED_CODES, FredSource
from ditto_datahub.sources.fred.indicators import (
    FRED_INDICATORS,
    FredIndicator,
    get_fred_indicator,
    list_fred_indicators,
)

__all__ = [
    "ALL_FRED_CODES",
    "FRED_INDICATORS",
    "FredClient",
    "FredIndicator",
    "FredSource",
    "MacroFredAdapter",
    "get_fred_indicator",
    "list_fred_indicators",
]
