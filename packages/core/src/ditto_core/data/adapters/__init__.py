"""Database adapters for different storage backends."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .duckdb_adapter import DuckDBAdapter

from .base import DatabaseAdapter
from .protocol import DatabaseAdapter as DatabaseAdapterProtocol
from .sqlite_adapter import SQLiteAdapter

# Try to import DuckDB adapter - may fail if duckdb is not installed
try:
    from .duckdb_adapter import DuckDBAdapter
except (ImportError, ModuleNotFoundError):
    DuckDBAdapter = None  # type: ignore

__all__ = [
    "DatabaseAdapter",
    "DatabaseAdapterProtocol",
    "DuckDBAdapter",
    "SQLiteAdapter",
]
