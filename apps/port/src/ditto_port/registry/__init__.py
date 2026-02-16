"""
依赖注入注册表.

Composition Root 模式：所有依赖在应用入口点（apps/port/）组装，
核心包（foundation、datahub、core）不依赖 dishka。

目录结构（按架构层组织）：
- infra/    : Infrastructure 层（配置、观测、通知）
- core/     : Core 层（DQ 引擎）
- datahub/  : DataHub 层（数据源、Store、Service）
- contexts/ : 上下文组合包（解决 ARCH-003/004）
"""

# Infrastructure 层
# Core 层
# Contexts 层 - 上下文组合包
from .contexts import IngestionBundle, create_ingestion_bundle
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
    "IngestionBundle",
    "MacroProvider",
    "MarketProvider",
    "MetadataProvider",
    "NotificationProvider",
    "ObservabilityProvider",
    "QualityProvider",
    "RuntimeProvider",
    "SourcesProvider",
    "create_ingestion_bundle",
]
