"""DataHub 层 - Unified Derived Query Provider."""

from pathlib import Path

from dishka import Provider, Scope, provide
from ditto_datahub.config.data_store import DataStoreSettings
from ditto_datahub.services import (
    DerivedCatalogService,
    DerivedQueryService,
)
from ditto_datahub.stores.sqlite_client import SQLiteClient

from ditto_port.services.derived import (
    DerivedInvalidationService,
    DerivedMaterializationService,
    DerivedQueryFacade,
    SQLiteCompileCacheService,
    StaticRuntimeModeResolver,
    UnavailableDerivedInputProvider,
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
    def derived_query_service(
        self,
        derived_catalog_service: DerivedCatalogService,
    ) -> DerivedQueryService:
        """Derived query contract service."""
        return DerivedQueryService(catalog_service=derived_catalog_service)

    @provide
    def compile_cache_service(
        self,
        sqlite_client: SQLiteClient,
    ) -> SQLiteCompileCacheService:
        """SQLite-backed compile cache service."""
        return SQLiteCompileCacheService(sqlite_client)

    @provide
    def derived_input_provider(self) -> UnavailableDerivedInputProvider:
        """Default runtime input seam until source loaders are wired."""
        return UnavailableDerivedInputProvider()

    @provide
    def derived_materialization_service(
        self,
        derived_catalog_service: DerivedCatalogService,
        compile_cache_service: SQLiteCompileCacheService,
        derived_input_provider: UnavailableDerivedInputProvider,
        settings: DataStoreSettings,
    ) -> DerivedMaterializationService:
        """Unified materialization service."""
        return DerivedMaterializationService(
            catalog_service=derived_catalog_service,
            compile_cache_service=compile_cache_service,
            input_provider=derived_input_provider,
            artifact_root=Path(settings.data_root),
        )

    @provide
    def derived_invalidation_service(
        self,
        derived_catalog_service: DerivedCatalogService,
        derived_materialization_service: DerivedMaterializationService,
    ) -> DerivedInvalidationService:
        """Invalidation fan-out and repair service."""
        return DerivedInvalidationService(
            catalog_service=derived_catalog_service,
            materialization_service=derived_materialization_service,
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
        )
