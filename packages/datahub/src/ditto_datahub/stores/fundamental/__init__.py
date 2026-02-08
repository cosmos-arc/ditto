"""Fundamental Domain - 企业基本面数据域."""

from ditto_datahub.stores.fundamental.fundamental_ingestion import (
    FundamentalIngestion,
)
from ditto_datahub.stores.fundamental.fundamental_store import FundamentalStore

__all__ = [
    "FundamentalIngestion",
    "FundamentalStore",
]
