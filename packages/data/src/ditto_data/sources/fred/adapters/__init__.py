"""FRED adapters package."""

from __future__ import annotations

from ditto_data.sources.fred.adapters.base import BaseFredAdapter
from ditto_data.sources.fred.adapters.commodity import CommodityFredAdapter
from ditto_data.sources.fred.adapters.macro import MacroFredAdapter

__all__ = [
    "BaseFredAdapter",
    "CommodityFredAdapter",
    "MacroFredAdapter",
]
