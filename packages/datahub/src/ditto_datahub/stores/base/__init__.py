"""Base store abstractions."""

from ditto_datahub.stores.base.base_store import BaseStore
from ditto_datahub.stores.base.parquet_store import ParquetStore

__all__ = [
    "BaseStore",
    "ParquetStore",
]
