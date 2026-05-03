"""
Base store abstractions.

Re-exports generic storage types from platform; data-specific types remain local.
"""

from ditto_platform.foundation.storage import (
    MergeResult,
    ParquetStore,
    PartitionStrategy,
    YearlyPartition,
)
from ditto_platform.foundation.storage.protocols import (
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
