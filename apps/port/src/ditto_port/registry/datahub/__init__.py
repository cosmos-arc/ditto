"""DataHub 层 Provider 聚合。"""

from dishka import Provider

from .capital import CapitalProvider
from .features import FeaturesProvider
from .fundamental import FundamentalProvider
from .macro import MacroProvider
from .market import MarketProvider
from .metadata import MetadataProvider
from .runtime import RuntimeProvider
from .sources import SourcesProvider

__all__ = [
    "CapitalProvider",
    "FeaturesProvider",
    "FundamentalProvider",
    "MacroProvider",
    "MarketProvider",
    "MetadataProvider",
    "RuntimeProvider",
    "SourcesProvider",
    "get_datahub_providers",
]


def get_datahub_providers() -> list[Provider]:
    """返回 DataHub 层的所有 Provider."""
    return [
        SourcesProvider(),
        RuntimeProvider(),
        MetadataProvider(),
        MarketProvider(),
        FundamentalProvider(),
        CapitalProvider(),
        MacroProvider(),
        FeaturesProvider(),
    ]
