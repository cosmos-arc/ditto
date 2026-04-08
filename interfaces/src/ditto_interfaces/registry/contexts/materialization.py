"""物化上下文工厂。"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from ditto_app.process.cascade_orchestrator import InvalidationCascadeOrchestrator
from ditto_app.process.materialization_orchestrator import (
    DerivedMaterializationOrchestrator,
)
from ditto_app.process.publication_facade import DerivedPublicationFacade
from ditto_app.query.research import ResearchDatasetFacade

from ditto_interfaces.registry.container import make_app_container
from ditto_interfaces.registry.contexts.bundle import MaterializationBundle


@contextmanager
def create_materialization_bundle() -> Iterator[MaterializationBundle]:
    """创建物化上下文组合包（单容器）。"""
    container = make_app_container()
    try:
        yield MaterializationBundle(
            materialization_service=container.get(DerivedMaterializationOrchestrator),
            invalidation_service=container.get(InvalidationCascadeOrchestrator),
            publication_facade=container.get(DerivedPublicationFacade),
            research_dataset_facade=container.get(ResearchDatasetFacade),
        )
    finally:
        container.close()
