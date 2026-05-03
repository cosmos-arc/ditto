"""Re-export storage protocols from platform (backward compat)."""

from ditto_platform.foundation.storage.protocols import (
    DatasetReader,
    DatasetWriter,
    SqliteReader,
    SqliteWriter,
)

__all__ = ["DatasetReader", "DatasetWriter", "SqliteReader", "SqliteWriter"]
