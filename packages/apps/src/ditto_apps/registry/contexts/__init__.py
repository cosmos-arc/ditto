"""上下文组合包模块。"""

from __future__ import annotations

from ditto_apps.registry.contexts.bundle import (
    ExperimentExecutionBundle,
    IngestionBundle,
    MaterializationBundle,
    ResearchBundle,
    StrategyBundle,
)
from ditto_apps.registry.contexts.ingestion import create_ingestion_bundle
from ditto_apps.registry.contexts.materialization import (
    create_materialization_bundle,
)
from ditto_apps.registry.contexts.query import QueryContext, create_query_context
from ditto_apps.registry.contexts.research import create_research_bundle
from ditto_apps.registry.contexts.research_execution import (
    create_experiment_tick_bundle,
)
from ditto_apps.registry.contexts.strategy import create_strategy_bundle

__all__ = [
    "ExperimentExecutionBundle",
    "IngestionBundle",
    "MaterializationBundle",
    "QueryContext",
    "ResearchBundle",
    "StrategyBundle",
    "create_experiment_tick_bundle",
    "create_ingestion_bundle",
    "create_materialization_bundle",
    "create_query_context",
    "create_research_bundle",
    "create_strategy_bundle",
]
