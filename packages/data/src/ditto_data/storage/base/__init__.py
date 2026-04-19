"""Base store abstractions."""

from ditto_data.storage.base.parquet_store import MergeResult, ParquetStore
from ditto_data.storage.base.partition_strategy import (
    PartitionStrategy,
    YearlyPartition,
)
from ditto_data.storage.base.protocols import (
    DatasetReader,
    DatasetWriter,
    SqliteReader,
    SqliteWriter,
)
from ditto_data.storage.base.sqlite_store import SQLiteStore

__all__ = [
    "DatasetReader",
    "DatasetWriter",
    "MergeResult",
    "ParquetStore",
    "PartitionStrategy",
    "SQLiteStore",
    "SqliteReader",
    "SqliteWriter",
    "YearlyPartition",
]
