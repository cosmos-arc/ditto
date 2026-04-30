"""物化上下文工厂。"""

from collections.abc import Generator
from contextlib import contextmanager

from ditto_application.process.materialization.cascade_orchestrator import (
    InvalidationCascadeOrchestrator,
)
from ditto_application.process.materialization.orchestrator import (
    DerivedMaterializationOrchestrator,
)
from ditto_application.process.materialization.publication_facade import (
    DerivedPublicationFacade,
)
from ditto_application.query.research import ResearchDatasetFacade

from ditto_apps.registry.container import make_app_container
from ditto_apps.registry.contexts.bundle import MaterializationBundle


@contextmanager
def create_materialization_bundle() -> Generator[MaterializationBundle, None, None]:
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
