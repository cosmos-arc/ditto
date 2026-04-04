"""Data 层 - Derived Query 基础设施 Provider."""

from pathlib import Path

from dishka import Provider, Scope, provide

from ditto_data.config.data_store import DataStoreSettings
from ditto_data.services import (
    DerivedArtifactReader,
    DerivedCatalogService,
    DerivedQueryService,
)
from ditto_data.services.research_artifact_service import ResearchArtifactService

__all__ = ["DerivedProvider"]


class DerivedProvider(Provider):
    """
    Data 层 Derived 基础设施 Provider.

    仅注册 Data 层服务，App 层服务（Facade/Orchestrator）
    已迁入 ditto_app.providers。
    """

    scope = Scope.APP

    @provide
    def research_artifact_service(
        self,
        settings: DataStoreSettings,
    ) -> ResearchArtifactService:
        """Research artifact file I/O service."""
        return ResearchArtifactService(artifact_root=Path(settings.data_root))

    @provide
    def derived_query_service(
        self,
        derived_catalog_service: DerivedCatalogService,
        settings: DataStoreSettings,
    ) -> DerivedQueryService:
        """Derived query contract service."""
        return DerivedQueryService(
            catalog_service=derived_catalog_service,
            artifact_reader=DerivedArtifactReader(
                catalog_service=derived_catalog_service,
                artifact_root=Path(settings.data_root),
            ),
        )
