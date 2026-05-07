"""
依赖注入注册表.

Composition Root 模式：所有依赖在 apps 入口组装。
DI Provider 已下沉至各业务包：
- ditto_data.di: Data 层 Provider（原 Data + Core DQ）
- ditto_application.providers: Application 层 Provider

目录结构：
- platform providers: 平台能力组合（配置、观测、通知）
- contexts/ : 上下文组合包（解决 ARCH-003/004）
"""

from __future__ import annotations

# Platform provider wiring
# Context bundle wiring
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
    "ConfigProvider",
    "IngestionBundle",
    "MaterializationBundle",
    "NotificationProvider",
    "ObservabilityProvider",
    "StrategyBundle",
    "create_ingestion_bundle",
    "create_materialization_bundle",
    "create_strategy_bundle",
]
