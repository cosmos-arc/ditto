"""
Data module for the Ditto quantitative trading system.

Provides a unified interface for data access, validation, and storage.
"""

__version__ = "0.1.0"

from .adapters import DuckDBAdapter, SQLiteAdapter
from .collector import DataCollector
from .quality_service import DataQualityService
from .service import DataService

__all__ = [
    "DataCollector",
    "DataQualityService",
    "DataService",
    "DuckDBAdapter",
    "SQLiteAdapter",
]
