"""Infrastructure 层 Provider 聚合。"""

from dishka import Provider

from .config import ConfigProvider
from .notification import NotificationProvider
from .observability import ObservabilityProvider

__all__ = [
    "ConfigProvider",
    "NotificationProvider",
    "ObservabilityProvider",
    "get_infra_providers",
]


def get_infra_providers() -> list[Provider]:
    """返回 Infrastructure 层的所有 Provider."""
    return [
        ConfigProvider(),
        ObservabilityProvider(),
        NotificationProvider(),
    ]
