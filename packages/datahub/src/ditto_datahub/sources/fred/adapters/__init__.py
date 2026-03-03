"""FRED adapters package."""

from __future__ import annotations

from ditto_datahub.sources.fred.adapters.base import BaseFredAdapter
from ditto_datahub.sources.fred.adapters.commodity import CommodityFredAdapter
from ditto_datahub.sources.fred.adapters.macro import MacroFredAdapter

__all__ = [
    "BaseFredAdapter",
    "CommodityFredAdapter",
    "MacroFredAdapter",
]
