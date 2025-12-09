"""
Ditto 核心模块.

包含量化系统的核心业务逻辑
"""

__version__ = "0.1.0"
__author__ = "Ditto Team"

from .data.adapters import DatabaseAdapter, DuckDBAdapter, SQLiteAdapter
from .data.constants import DatabaseType, DataSourceType
from .data.datasources import AkShareDataSource, DataSource, TushareDataSource

__all__ = [
    "DatabaseAdapter",
    "DatabaseType",
    "DataSource",
    "DataSourceType",
    "DuckDBAdapter",
    "SQLiteAdapter",
    "AkShareDataSource",
    "TushareDataSource",
]
