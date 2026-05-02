"""Analysis 层 DI Provider."""

from dishka import Provider

from .storage import AnalysisStorageProvider

__all__ = ["AnalysisStorageProvider", "get_analysis_providers"]


def get_analysis_providers() -> list[Provider]:
    """返回 Analysis 层的所有 Provider."""
    return [AnalysisStorageProvider()]
