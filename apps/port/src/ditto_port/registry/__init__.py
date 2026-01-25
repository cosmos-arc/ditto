"""
依赖注入注册表.

Composition Root 模式：所有依赖在应用入口点（apps/port/）组装，
核心包（foundation、datahub、core）不依赖 dishka。
"""

from ditto_port.registry.app import AppProvider
from ditto_port.registry.config import ConfigProvider
from ditto_port.registry.core import CoreProvider
from ditto_port.registry.datahub import DataHubProvider
from ditto_port.registry.notification import NotificationProvider
from ditto_port.registry.sources import DataSourcesProvider

__all__ = [
    "AppProvider",
    "ConfigProvider",
    "CoreProvider",
    "DataHubProvider",
    "DataSourcesProvider",
    "NotificationProvider",
]
