"""
依赖注入注册表.

Composition Root 模式：所有依赖在应用入口点（apps/port/）组装，
核心包（foundation、datahub、core）不依赖 dishka。
"""

from ditto_port.registry.app import AppProvider
from ditto_port.registry.datahub import DataHubProvider

__all__ = ["AppProvider", "DataHubProvider"]
