"""物化上下文工厂。"""

from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import asdict

from ditto_application.commands.research_dataset_export import ResearchDatasetExport
from ditto_application.processes.materialization.orchestrator import (
    DerivedMaterializationOrchestrator,
)
from ditto_application.processes.research_dataset import ResearchDatasetBuildProcess
from ditto_application.queries.research import ResearchDatasetQuery
from ditto_features.materialization.contracts import DerivedMaterializationRequest
from ditto_features.materialization.models import DerivedRunMode, DerivedRunTrigger
from ditto_features.services.derived_catalog_service import DerivedCatalogService
from ditto_features.services.spec_registration import register_governed_factor

from ditto_apps.registry.container import make_app_container
from ditto_apps.registry.contexts.bundle import MaterializationBundle


@contextmanager
def create_materialization_bundle() -> Generator[MaterializationBundle]:
    """创建物化上下文组合包（单容器）。"""
    container = make_app_container()
    try:
        yield MaterializationBundle(
            materialization_service=container.get(DerivedMaterializationOrchestrator),
            research_dataset_build=container.get(ResearchDatasetBuildProcess),
            research_dataset_query=container.get(ResearchDatasetQuery),
            research_dataset_export=container.get(ResearchDatasetExport),
        )
    finally:
        container.close()


def materialize_governed_factor(
    *, factor: str, version: int, mode: str, start: str, end: str
) -> dict[str, object]:
    """Compose governed registration and execution behind the CLI boundary."""
    container = make_app_container()
    try:
        registration = register_governed_factor(
            container.get(DerivedCatalogService), factor, version=version
        )
        result = container.get(DerivedMaterializationOrchestrator).materialize(
            DerivedMaterializationRequest(
                derived_id=registration.derived_id,
                version=registration.version,
                mode=DerivedRunMode(mode),
                request_start=start,
                request_end=end,
                trigger=DerivedRunTrigger.MANUAL,
                source_snapshot_id=None,
            )
        )
        return {"registration": asdict(registration), "run": asdict(result)}
    finally:
        container.close()
