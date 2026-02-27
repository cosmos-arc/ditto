"""Adapters for Tushare data sources."""

from __future__ import annotations

from ditto_datahub.sources.tushare.adapters.base import BaseTushareAdapter
from ditto_datahub.sources.tushare.adapters.bond_yield import (
    CN_BOND_YIELD_INDICATORS,
    BondYieldTushareAdapter,
    CnBondYieldIndicator,
    get_cn_bond_yield_indicator,
)
from ditto_datahub.sources.tushare.adapters.calendar import CalendarTushareAdapter
from ditto_datahub.sources.tushare.adapters.capital import CapitalTushareAdapter
from ditto_datahub.sources.tushare.adapters.etf import ETFTushareAdapter
from ditto_datahub.sources.tushare.adapters.fx import (
    FX_CODE_TO_INSTRUMENT_ID,
    FxTushareAdapter,
)
from ditto_datahub.sources.tushare.adapters.industry import IndustryTushareAdapter
from ditto_datahub.sources.tushare.adapters.macro import MacroTushareAdapter
from ditto_datahub.sources.tushare.adapters.stock import StockTushareAdapter

__all__ = [
    "CN_BOND_YIELD_INDICATORS",
    "FX_CODE_TO_INSTRUMENT_ID",
    "BaseTushareAdapter",
    "BondYieldTushareAdapter",
    "CalendarTushareAdapter",
    "CapitalTushareAdapter",
    "CnBondYieldIndicator",
    "ETFTushareAdapter",
    "FxTushareAdapter",
    "IndustryTushareAdapter",
    "MacroTushareAdapter",
    "StockTushareAdapter",
    "get_cn_bond_yield_indicator",
]
