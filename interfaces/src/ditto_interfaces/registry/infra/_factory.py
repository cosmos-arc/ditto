"""Infrastructure 层 Provider 工厂."""

from __future__ import annotations

from dishka import Provider

from .config import ConfigProvider
from .notification import NotificationProvider
from .observability import ObservabilityProvider
from .signal_delivery import SignalDeliveryProvider

__all__ = ["get_infra_providers"]


def get_infra_providers() -> list[Provider]:
    """返回 Infrastructure 层的所有 Provider."""
    return [
        ConfigProvider(),
        ObservabilityProvider(),
        NotificationProvider(),
        SignalDeliveryProvider(),
    ]
