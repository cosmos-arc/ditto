"""
依赖注入注册表.

Composition Root 模式：所有依赖在应用入口点（apps/port/）组装，
核心包（foundation、datahub、core）不依赖 dishka。

目录结构（按架构层组织）：
- infra/    : Infrastructure 层（配置、观测、通知）
- core/     : Core 层（DQ 引擎）
- datahub/  : DataHub 层（数据源、Store、Service）
"""

# Infrastructure 层
# Core 层
from .core import QualityProvider

# DataHub 层
from .datahub import (
    CapitalProvider,
    FeaturesProvider,
    FundamentalProvider,
    MacroProvider,
    MarketProvider,
    MetadataProvider,
    RuntimeProvider,
    SourcesProvider,
)
from .infra import (
    ConfigProvider,
    NotificationProvider,
    ObservabilityProvider,
)

__all__ = [
    "CapitalProvider",
    "ConfigProvider",
    "FeaturesProvider",
    "FundamentalProvider",
    "MacroProvider",
    "MarketProvider",
    "MetadataProvider",
    "NotificationProvider",
    "ObservabilityProvider",
    "QualityProvider",
    "RuntimeProvider",
    "SourcesProvider",
]
