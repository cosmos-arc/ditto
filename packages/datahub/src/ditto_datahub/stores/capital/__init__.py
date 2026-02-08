"""Capital Domain - 资金与资本市场数据域."""

from ditto_datahub.stores.capital.capital_ingestion import (
    CapitalIngestion,
    IngestionResult,
)
from ditto_datahub.stores.capital.capital_store import CapitalStore

__all__ = [
    "CapitalIngestion",
    "CapitalStore",
    "IngestionResult",
]
