"""Base store abstractions."""

from ditto_data.stores.base.base_store import BaseStore
from ditto_data.stores.base.parquet_store import MergeResult, ParquetStore
from ditto_data.stores.base.partition_strategy import (
    PartitionStrategy,
    YearlyPartition,
)
from ditto_data.stores.base.sqlite_store import SQLiteStore

__all__ = [
    "BaseStore",
    "MergeResult",
    "ParquetStore",
    "PartitionStrategy",
    "SQLiteStore",
    "YearlyPartition",
]
