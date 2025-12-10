"""Data source implementations."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .akshare import AkShareDataSource
    from .tushare import TushareDataSource

# Try importing datasources - may fail if dependencies are not installed
try:
    from .akshare import AkShareDataSource
except ImportError:
    AkShareDataSource = None  # type: ignore

try:
    from .tushare import TushareDataSource
except ImportError:
    TushareDataSource = None  # type: ignore

from .base import DataSource
from .factory import DataSourceFactory

__all__ = [
    "AkShareDataSource",
    "DataSource",
    "DataSourceFactory",
    "TushareDataSource",
]
