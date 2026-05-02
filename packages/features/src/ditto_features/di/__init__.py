"""Features 层 DI Provider."""

from __future__ import annotations

from dishka import Provider

from .storage import FeaturesStorageProvider

__all__ = ["FeaturesStorageProvider", "get_features_providers"]


def get_features_providers() -> list[Provider]:
    """返回 Features 层的所有 Provider."""
    return [FeaturesStorageProvider()]
