"""Adapters for Tushare data sources."""

from __future__ import annotations

from ditto_datahub.sources.tushare.adapters.base import BaseTushareAdapter
from ditto_datahub.sources.tushare.adapters.calendar import CalendarTushareAdapter
from ditto_datahub.sources.tushare.adapters.capital import CapitalTushareAdapter
from ditto_datahub.sources.tushare.adapters.etf import ETFTushareAdapter
from ditto_datahub.sources.tushare.adapters.industry import IndustryTushareAdapter
from ditto_datahub.sources.tushare.adapters.macro import MacroTushareAdapter
from ditto_datahub.sources.tushare.adapters.stock import StockTushareAdapter

__all__ = [
    "BaseTushareAdapter",
    "CalendarTushareAdapter",
    "CapitalTushareAdapter",
    "ETFTushareAdapter",
    "IndustryTushareAdapter",
    "MacroTushareAdapter",
    "StockTushareAdapter",
]
