"""上下文组合包模块。"""

from __future__ import annotations

from ditto_interfaces.registry.contexts.bundle import (
    IngestionBundle,
    MaterializationBundle,
    StrategyBundle,
)
from ditto_interfaces.registry.contexts.ingestion import create_ingestion_bundle
from ditto_interfaces.registry.contexts.materialization import (
    create_materialization_bundle,
)
from ditto_interfaces.registry.contexts.strategy import create_strategy_bundle

__all__ = [
    "IngestionBundle",
    "MaterializationBundle",
    "StrategyBundle",
    "create_ingestion_bundle",
    "create_materialization_bundle",
    "create_strategy_bundle",
]
