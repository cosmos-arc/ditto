"""Generic storage infrastructure shared across packages."""

from ditto_platform.foundation.storage.parquet_store import ParquetStore
from ditto_platform.foundation.storage.parquet_write import MergeResult
from ditto_platform.foundation.storage.partition_strategy import (
    PartitionStrategy,
    YearlyPartition,
)
from ditto_platform.foundation.storage.protocols import (
    DatasetReader,
    DatasetWriter,
    SqliteReader,
    SqliteWriter,
)
from ditto_platform.foundation.storage.sqlite_client import SQLiteClient
from ditto_platform.foundation.storage.types import (
    OnDuplicate,
    WriteResult,
    WriteStoreResult,
)

__all__ = [
    "DatasetReader",
    "DatasetWriter",
    "MergeResult",
    "OnDuplicate",
    "ParquetStore",
    "PartitionStrategy",
    "SQLiteClient",
    "SqliteReader",
    "SqliteWriter",
    "WriteResult",
    "WriteStoreResult",
    "YearlyPartition",
]
