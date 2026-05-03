"""Re-export SQLiteClient from platform (backward compat)."""

from ditto_platform.foundation.storage.sqlite_client import (
    SQLiteClient,
)

__all__ = ["SQLiteClient"]
