"""
Data 层 DI Provider 聚合.

将所有 Data 层的 Dishka Provider 统一注册，
由 Composition Root（registry/container.py）通过此模块导入。
"""

from ._factory import get_data_providers
from .builders import parquet_store_pair, sqlite_store_pair
from .capital import CapitalProvider
from .derived import DerivedProvider
from .fundamental import FundamentalProvider
from .golden import GoldenDatasetProvider
from .macro import MacroProvider
from .market import MarketProvider
from .metadata import MetadataProvider
from .quality import QualityProvider
from .runtime import RuntimeProvider
from .sources import SourcesProvider
from .trade import TradeProvider

__all__ = [
    "CapitalProvider",
    "DerivedProvider",
    "FundamentalProvider",
    "GoldenDatasetProvider",
    "MacroProvider",
    "MarketProvider",
    "MetadataProvider",
    "QualityProvider",
    "RuntimeProvider",
    "SourcesProvider",
    "TradeProvider",
    "get_data_providers",
    "parquet_store_pair",
    "sqlite_store_pair",
]
