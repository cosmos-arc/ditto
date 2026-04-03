"""
依赖注入注册表.

Composition Root 模式：所有依赖在应用入口点（apps/interfaces/）组装。
DI Provider 已下沉至各业务包：
- ditto_data.di: Data 层 Provider（原 DataHub + Core DQ）
- ditto_app.providers: App 层 Provider

目录结构：
- infra/    : Infrastructure 层（配置、观测、通知）
- contexts/ : 上下文组合包（解决 ARCH-003/004）
"""

# Infrastructure 层
# Data 层（从 ditto_data.di re-export）
from ditto_data.di import (
    CapitalProvider,
    DerivedProvider,
    FundamentalProvider,
    GoldenDatasetProvider,
    MacroProvider,
    MarketProvider,
    MetadataProvider,
    QualityProvider,
    RuntimeProvider,
    SourcesProvider,
)

# Contexts 层
from .contexts import (
    IngestionBundle,
    MaterializationBundle,
    StrategyBundle,
    create_ingestion_bundle,
    create_materialization_bundle,
    create_strategy_bundle,
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
    "GoldenDatasetProvider",
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
