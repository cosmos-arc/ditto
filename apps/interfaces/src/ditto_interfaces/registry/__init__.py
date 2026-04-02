"""
依赖注入注册表.

Composition Root 模式：所有依赖在应用入口点（apps/port/）组装，
核心包（foundation、datahub、core）不依赖 dishka。

目录结构（按架构层组织）：
- infra/    : Infrastructure 层（配置、观测、通知）
- core/     : Core 层（DQ 引擎）
- datahub/  : DataHub 层（数据源、Store、Service）
- port/     : Port 层（已空，App 层服务迁入 ditto_app.providers）
- contexts/ : 上下文组合包（解决 ARCH-003/004）
"""

# Infrastructure 层
# Contexts 层 - 上下文组合包
from .contexts import (
    IngestionBundle,
    MaterializationBundle,
    StrategyBundle,
    create_ingestion_bundle,
    create_materialization_bundle,
    create_strategy_bundle,
)

# Core 层
from .core import QualityProvider

# DataHub 层
from .datahub import (
    CapitalProvider,
    DerivedProvider,
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
    "DerivedProvider",
    "FundamentalProvider",
    "IngestionBundle",
    "MacroProvider",
    "MarketProvider",
    "MaterializationBundle",
    "MetadataProvider",
    "NotificationProvider",
    "ObservabilityProvider",
    "QualityProvider",
    "RuntimeProvider",
    "SourcesProvider",
    "StrategyBundle",
    "create_ingestion_bundle",
    "create_materialization_bundle",
    "create_strategy_bundle",
]
