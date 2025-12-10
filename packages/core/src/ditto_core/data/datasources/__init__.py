"""Data source implementations."""

# Try importing datasources - may fail if dependencies are not installed
try:
    from .akshare import AkShareDataSource
except ImportError:
    AkShareDataSource = None

try:
    from .tushare import TushareDataSource
except ImportError:
    TushareDataSource = None

from .base import DataSource
from .factory import DataSourceFactory

__all__ = [
    "AkShareDataSource",
    "DataSource",
    "DataSourceFactory",
    "TushareDataSource",
]
