"""数据访问层模块"""

from .service import DataService
from .adapters import DuckDBAdapter, SQLiteAdapter

__all__ = [
    "DataService",
    "DuckDBAdapter",
    "SQLiteAdapter",
]