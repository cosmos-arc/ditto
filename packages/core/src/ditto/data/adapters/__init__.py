"""数据库适配器模块"""

from .duckdb_adapter import DuckDBAdapter
from .sqlite_adapter import SQLiteAdapter

__all__ = [
    "DuckDBAdapter",
    "SQLiteAdapter",
]