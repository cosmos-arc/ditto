"""
Ditto 核心模块.

包含量化系统的核心业务逻辑
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .data.datasources import AkShareDataSource, TushareDataSource

__version__ = "0.1.0"
__author__ = "Ditto Team"

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
    "DatabaseType",
    "TushareDataSource",
]
