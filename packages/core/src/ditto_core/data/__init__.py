"""
Data module for the Ditto quantitative trading system.

Provides a unified interface for data access, validation, and storage.
"""

__version__ = "0.1.0"

from .collector import DataCollector
from .constants import DatabaseType, DataSourceType
from .datasources import (
    AkShareDataSource,
    DataSource,
    DataSourceFactory,
    TushareDataSource,
)
from .quality_service import DataQualityService

__all__ = [
    "AkShareDataSource",
    "DataCollector",
    "DataQualityService",
    "DataSource",
    "DataSourceFactory",
    "DataSourceType",
    "DatabaseType",
    "TushareDataSource",
]
