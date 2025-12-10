"""Database adapters for different storage backends."""

from .base import DatabaseAdapter
from .protocol import DatabaseAdapter as DatabaseAdapterProtocol
from .sqlite_adapter import SQLiteAdapter

# Try to import DuckDB adapter - may fail if duckdb is not installed
try:
    from .duckdb_adapter import DuckDBAdapter
except (ImportError, ModuleNotFoundError):
    DuckDBAdapter = None

__all__ = [
    "DatabaseAdapter",
    "DatabaseAdapterProtocol",
    "DuckDBAdapter",
    "SQLiteAdapter",
]
