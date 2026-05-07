"""上下文组合包模块。"""

from __future__ import annotations

from ditto_apps.registry.contexts.bundle import (
    IngestionBundle,
    MaterializationBundle,
    StrategyBundle,
)
from ditto_apps.registry.contexts.ingestion import create_ingestion_bundle
from ditto_apps.registry.contexts.materialization import (
    create_materialization_bundle,
)
from ditto_apps.registry.contexts.query import QueryContext, create_query_context
from ditto_apps.registry.contexts.strategy import create_strategy_bundle

__all__ = [
    "IngestionBundle",
    "MaterializationBundle",
    "QueryContext",
    "StrategyBundle",
    "create_ingestion_bundle",
    "create_materialization_bundle",
    "create_query_context",
    "create_strategy_bundle",
]
