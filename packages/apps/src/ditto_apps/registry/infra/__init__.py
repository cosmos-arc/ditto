"""Infrastructure 层 Provider 聚合。"""

from __future__ import annotations

from ._factory import get_infra_providers
from .config import ConfigProvider
from .init_providers import MetadataDbInitProvider
from .notification import NotificationProvider
from .observability import ObservabilityProvider
from .protocol_adapters import ProtocolAdapterProvider, R2LiveGateEvidenceProvider
from .signal_delivery import SignalDeliveryProvider

__all__ = [
    "ConfigProvider",
    "MetadataDbInitProvider",
    "NotificationProvider",
    "ObservabilityProvider",
    "ProtocolAdapterProvider",
    "R2LiveGateEvidenceProvider",
    "SignalDeliveryProvider",
    "get_infra_providers",
]
