"""Data 层 DI Provider 工厂."""

from __future__ import annotations

from dishka import Provider

from .capital import CapitalProvider
from .fundamental import FundamentalProvider
from .golden import GoldenDatasetProvider
from .macro import MacroProvider
from .market import MarketProvider
from .metadata import MetadataProvider
from .quality import QualityProvider
from .runtime import RuntimeProvider
from .sources import SourcesProvider

__all__ = ["get_data_providers"]


def get_data_providers() -> list[Provider]:
    """
    返回 Data 层的所有 Provider.

    包含 Data 层的 9 个 Provider。
    非 Data 能力包的存储 DI
    由各自包的 di/ 模块提供。
    """
    return [
        SourcesProvider(),
        RuntimeProvider(),
        MetadataProvider(),
        MarketProvider(),
        FundamentalProvider(),
        CapitalProvider(),
        MacroProvider(),
        GoldenDatasetProvider(),
        QualityProvider(),
    ]
