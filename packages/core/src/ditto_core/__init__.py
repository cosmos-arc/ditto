"""
Ditto 核心模块.

包含量化系统的核心业务逻辑
"""

__version__ = "0.1.0"
__author__ = "Ditto Team"

from .data.adapters import DatabaseAdapter, SQLiteAdapter

# Try to import DuckDB adapter - may fail if duckdb is not installed
try:
    from .data.adapters import DuckDBAdapter
except (ImportError, ModuleNotFoundError):
    DuckDBAdapter = None
from .data.constants import DatabaseType, DataSourceType
from .data.datasources import (
    AkShareDataSource,
    DataSource,
    DataSourceFactory,
    TushareDataSource,
)

__all__ = [
    "AkShareDataSource",
    "DataSource",
    "DataSourceFactory",
    "DataSourceType",
    "DatabaseAdapter",
    "DatabaseType",
    "DuckDBAdapter",
    "SQLiteAdapter",
    "TushareDataSource",
]
