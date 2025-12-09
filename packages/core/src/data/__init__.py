"""
Data module for the Ditto quantitative trading system.

Provides a unified interface for data access, validation, and storage.
"""

__version__ = "0.1.0"

from .service import DataService
from .adapters import DuckDBAdapter, SQLiteAdapter
from .quality_service import DataQualityService
from .collector import DataCollector

__all__ = [
    "DataService",
    "DuckDBAdapter",
    "SQLiteAdapter",
    "DataQualityService",
    "DataCollector",
]