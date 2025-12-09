"""Database adapters for different storage backends."""

from .base import DatabaseAdapter
from .duckdb_adapter import DuckDBAdapter
from .protocol import DatabaseAdapter as DatabaseAdapterProtocol
from .sqlite_adapter import SQLiteAdapter

__all__ = [
    "DatabaseAdapter",
    "DatabaseAdapterProtocol",
    "DuckDBAdapter",
    "SQLiteAdapter",
]
