"""Port 层 Provider 聚合。"""

from dishka import Provider

from .strategy import StrategyProvider

__all__ = ["StrategyProvider", "get_port_providers"]


def get_port_providers() -> list[Provider]:
    """返回 Port 层所有 Provider。"""
    return [StrategyProvider()]
