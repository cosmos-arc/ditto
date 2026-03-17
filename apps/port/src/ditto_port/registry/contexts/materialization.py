"""物化上下文工厂。"""

from collections.abc import Iterator
from contextlib import contextmanager

from ditto_port.registry.container import make_app_container
from ditto_port.registry.contexts.bundle import MaterializationBundle
from ditto_port.services.derived import (
    DerivedInvalidationOrchestrator,
    DerivedMaterializationOrchestrator,
    DerivedPublicationFacade,
    ResearchDatasetFacade,
)


@contextmanager
def create_materialization_bundle() -> Iterator[MaterializationBundle]:
    """创建物化上下文组合包（单容器）。"""
    container = make_app_container()
    try:
        yield MaterializationBundle(
            materialization_service=container.get(DerivedMaterializationOrchestrator),
            invalidation_service=container.get(DerivedInvalidationOrchestrator),
            publication_facade=container.get(DerivedPublicationFacade),
            research_dataset_facade=container.get(ResearchDatasetFacade),
        )
    finally:
        container.close()
