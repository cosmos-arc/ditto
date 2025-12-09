"""Database adapters for different storage backends."""

from .duckdb_adapter import DuckDBAdapter
from .sqlite_adapter import SQLiteAdapter

__all__ = [
    "DuckDBAdapter",
    "SQLiteAdapter",
]
