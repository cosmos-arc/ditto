"""
Data module for the Ditto quantitative trading system.

Provides a unified interface for data access, validation, and storage.
"""

__version__ = "0.1.0"

from .adapters import DatabaseAdapter, DuckDBAdapter, SQLiteAdapter
from .collector import DataCollector
from .constants import DatabaseType, DataSourceType
from .datasources import AkShareDataSource, DataSource, DataSourceFactory, TushareDataSource
from .quality_service import DataQualityService
from .service import DataService

__all__ = [
    "AkShareDataSource",
    "DataCollector",
    "DataQualityService",
    "DataService",
    "DataSource",
    "DataSourceFactory",
    "DataSourceType",
    "DatabaseAdapter",
    "DatabaseType",
    "DuckDBAdapter",
    "SQLiteAdapter",
    "TushareDataSource",
]
