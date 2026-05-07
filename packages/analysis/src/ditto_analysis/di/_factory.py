"""Analysis 层 DI Provider 工厂."""

from __future__ import annotations

from dishka import Provider

from .storage import AnalysisStorageProvider

__all__ = ["get_analysis_providers"]


def get_analysis_providers() -> list[Provider]:
    """返回 Analysis 层的所有 Provider."""
    return [AnalysisStorageProvider()]
