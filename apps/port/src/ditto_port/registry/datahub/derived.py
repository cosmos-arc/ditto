"""DataHub 层 - Unified Derived Query Provider."""

from pathlib import Path

from dishka import Provider, Scope, provide
from ditto_core.engine import SQLiteCompileCache
from ditto_datahub.config.data_store import DataStoreSettings
from ditto_datahub.services import (
    DerivedArtifactReader,
    DerivedCatalogService,
    DerivedQueryService,
    DerivedShadowSlotService,
    PublicationSafetyRecordService,
    ResearchCatalogService,
)
from ditto_datahub.services.derived.artifact_persistence_service import (
    ArtifactPersistenceService,
)
from ditto_datahub.services.hot_layer import UnavailableHotLayerReader
from ditto_datahub.services.market_service import MarketService
from ditto_datahub.services.metadata_service import MetadataService
from ditto_datahub.services.research_artifact_service import ResearchArtifactService
from ditto_datahub.stores.sqlite_client import SQLiteClient

from ditto_port.services.derived import (
    DerivedPublicationFacade,
    DerivedQueryFacade,
    InvalidationCascadeOrchestrator,
    ResearchDatasetFacade,
    RuntimeDerivedInputProvider,
    StaticRuntimeModeResolver,
)
from ditto_port.services.derived.materialization_orchestrator import (
    DerivedMaterializationOrchestrator,
)

__all__ = ["DerivedProvider"]


class DerivedProvider(Provider):
    """Unified derived query provider."""

    scope = Scope.APP

    @provide
    def runtime_mode_resolver(self) -> StaticRuntimeModeResolver:
        """Static runtime mode resolver for Phase 2 contract wiring."""
        return StaticRuntimeModeResolver()

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

    @provide
    def compile_cache_service(
        self,
        sqlite_client: SQLiteClient,
    ) -> SQLiteCompileCache:
        """SQLite-backed compile cache service."""
        return SQLiteCompileCache(sqlite_client)

    @provide
    def derived_input_provider(
        self,
        derived_catalog_service: DerivedCatalogService,
        market_service: MarketService,
        settings: DataStoreSettings,
    ) -> RuntimeDerivedInputProvider:
        """Runtime input provider backed by truth-layer parquet and artifacts."""
        return RuntimeDerivedInputProvider(
            catalog_service=derived_catalog_service,
            market_service=market_service,
            artifact_root=Path(settings.data_root),
            data_root=Path(settings.data_root),
        )

    @provide
    def derived_materialization_orchestrator(
        self,
        derived_catalog_service: DerivedCatalogService,
        compile_cache_service: SQLiteCompileCache,
        derived_input_provider: RuntimeDerivedInputProvider,
        publication_record_service: PublicationSafetyRecordService,
        metadata_service: MetadataService,
        settings: DataStoreSettings,
    ) -> DerivedMaterializationOrchestrator:
        """Unified materialization orchestrator."""
        return DerivedMaterializationOrchestrator(
            catalog_service=derived_catalog_service,
            compile_cache_service=compile_cache_service,
            artifact_writer=ArtifactPersistenceService(
                artifact_root=Path(settings.data_root),
            ),
            input_provider=derived_input_provider,
            universe_provider=metadata_service,
            publication_record_service=publication_record_service,
        )

    @provide
    def derived_invalidation_orchestrator(
        self,
        derived_catalog_service: DerivedCatalogService,
        derived_materialization_orchestrator: DerivedMaterializationOrchestrator,
    ) -> InvalidationCascadeOrchestrator:
        """BFS-based invalidation cascade with cycle guard and state machine."""
        return InvalidationCascadeOrchestrator(
            catalog_service=derived_catalog_service,
            materialization_service=derived_materialization_orchestrator,
        )

    @provide
    def derived_query_facade(
        self,
        derived_query_service: DerivedQueryService,
        runtime_mode_resolver: StaticRuntimeModeResolver,
    ) -> DerivedQueryFacade:
        """Derived query use-case facade."""
        return DerivedQueryFacade(
            service=derived_query_service,
            mode_resolver=runtime_mode_resolver,
            hot_layer=UnavailableHotLayerReader(),
        )

    @provide
    def research_dataset_facade(
        self,
        metadata_service: MetadataService,
        research_catalog_service: ResearchCatalogService,
        derived_catalog_service: DerivedCatalogService,
        research_artifact_service: ResearchArtifactService,
        settings: DataStoreSettings,
    ) -> ResearchDatasetFacade:
        """Research dataset snapshot builder facade."""
        return ResearchDatasetFacade(
            metadata_service=metadata_service,
            research_catalog_service=research_catalog_service,
            artifact_reader=DerivedArtifactReader(
                catalog_service=derived_catalog_service,
                artifact_root=Path(settings.data_root),
            ),
            research_artifact_service=research_artifact_service,
        )

    @provide
    def derived_publication_facade(
        self,
        derived_catalog_service: DerivedCatalogService,
        publication_record_service: PublicationSafetyRecordService,
        shadow_slot_service: DerivedShadowSlotService,
        settings: DataStoreSettings,
    ) -> DerivedPublicationFacade:
        """Publication orchestration facade."""
        return DerivedPublicationFacade(
            catalog_service=derived_catalog_service,
            artifact_reader=DerivedArtifactReader(
                catalog_service=derived_catalog_service,
                artifact_root=Path(settings.data_root),
            ),
            publication_record_service=publication_record_service,
            shadow_slot_service=shadow_slot_service,
        )
