"""Adapters for Tushare data sources."""

from __future__ import annotations

from ditto_datahub.sources.tushare.adapters.base import BaseTushareAdapter
from ditto_datahub.sources.tushare.adapters.calendar import CalendarTushareAdapter
from ditto_datahub.sources.tushare.adapters.etf import ETFTushareAdapter
from ditto_datahub.sources.tushare.adapters.stock import StockTushareAdapter
from ditto_datahub.sources.tushare.adapters.stock_status import StockStatusAdapter

__all__ = [
    "BaseTushareAdapter",
    "CalendarTushareAdapter",
    "ETFTushareAdapter",
    "StockStatusAdapter",
    "StockTushareAdapter",
]
