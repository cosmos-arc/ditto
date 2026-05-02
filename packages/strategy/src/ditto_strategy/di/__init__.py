"""Strategy 层 DI Provider."""

from __future__ import annotations

from dishka import Provider

from .storage import StrategyStorageProvider

__all__ = ["StrategyStorageProvider", "get_strategy_providers"]


def get_strategy_providers() -> list[Provider]:
    """返回 Strategy 层的所有 Provider."""
    return [StrategyStorageProvider()]
