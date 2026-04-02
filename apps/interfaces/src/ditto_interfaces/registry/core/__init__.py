"""Core 层 Provider 聚合。"""

from dishka import Provider

from .golden import GoldenDatasetProvider
from .quality import QualityProvider

__all__ = ["GoldenDatasetProvider", "QualityProvider", "get_core_providers"]


def get_core_providers() -> list[Provider]:
    """返回 Core 层的所有 Provider."""
    return [GoldenDatasetProvider(), QualityProvider()]
