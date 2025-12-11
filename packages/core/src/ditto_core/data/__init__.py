"""
Data module for the Ditto quantitative trading system.

Provides a unified interface for data access, validation, and storage.
"""

import warnings

__version__ = "0.1.0"

from .adapters import DatabaseAdapter, DuckDBAdapter, SQLiteAdapter
from .collector import DataCollector
from .constants import DatabaseType, DataSourceType
from .datasources import (
    AkShareDataSource,
    DataSource,
    DataSourceFactory,
    TushareDataSource,
)
from .quality_service import DataQualityService
from .service import DataService

# Deprecation warning for DataService import
warnings.warn(
    "DataService is deprecated and will be removed in a future version. "
    "Use DataReader and DataWriter classes instead. "
    "Import them from ditto_core.data.services.data_reader and "
    "ditto_core.data.services.data_writer",
    DeprecationWarning,
    stacklevel=2,
)

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
