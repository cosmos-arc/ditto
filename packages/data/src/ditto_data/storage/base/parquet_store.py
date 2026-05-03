"""Re-export ParquetStore from platform (backward compat)."""

from ditto_platform.foundation.storage.parquet_store import (
    MergeResult,
    ParquetStore,
)

__all__ = ["MergeResult", "ParquetStore"]
