"""
Protocol adapters — bridge concrete infrastructure types to Protocol interfaces.

Composition root responsibility: concrete types live in data/platform/features DI;
application providers only depend on Protocol interfaces.  This module closes the
gap so Dishka can resolve Protocol-typed parameters without structural subtyping.
"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager
from importlib import import_module
from typing import Protocol, cast

from dishka import Provider, Scope, provide
from ditto_application.commands.catalog_remediation import (
    CatalogRemediationIngestDatePort,
)
from ditto_application.contracts import IngestDateCommand
from ditto_application.queries.source import SourceDataPort
from ditto_data.quality.protocols import (
    ComparisonStoreProtocol,
    InstrumentStoreProtocol,
    TdxSourceProtocol,
)
from ditto_data.services.source_accessor import SourceAccessor
from ditto_data.sources.tdx.source import TdxSource
from ditto_data.storage.metadata.instrument import InstrumentReader
from ditto_data.storage.runtime.quality import ComparisonWriter
from ditto_features.compile_cache import SQLiteCompileCacheBackend
from ditto_platform.foundation import SQLiteClient


class _IngestionCoordinatorLike(Protocol):
    def ingest_date(self, dataset: str, trade_date: str, force: bool = False) -> object:
        """Run one date-level ingestion."""
        ...


class _IngestionBundleLike(Protocol):
    coordinator: _IngestionCoordinatorLike


type _IngestionBundleFactory = Callable[
    ...,
    AbstractContextManager[_IngestionBundleLike],
]


def _ingestion_bundle_factory() -> _IngestionBundleFactory:
    module = import_module("ditto_apps.registry.contexts.ingestion")
    return cast(_IngestionBundleFactory, module.create_ingestion_bundle)


class _CatalogRemediationIngestDateAdapter:
    """Lazy adapter from remediation execution to the existing ingestion bundle."""

    def handle(self, command: IngestDateCommand) -> object:
        create_ingestion_bundle = _ingestion_bundle_factory()
        with create_ingestion_bundle(source="auto") as bundle:
            return bundle.coordinator.ingest_date(
                command.dataset,
                command.trade_date.isoformat(),
                command.force,
            )


class ProtocolAdapterProvider(Provider):
    """Bridges concrete infrastructure types to Protocol interfaces."""

    scope = Scope.APP

    @provide
    def tdx_source_protocol(self, source: TdxSource) -> TdxSourceProtocol:
        """TDX source → TdxSourceProtocol."""
        return source

    @provide
    def comparison_store_protocol(
        self,
        writer: ComparisonWriter,
    ) -> ComparisonStoreProtocol:
        """ComparisonWriter → ComparisonStoreProtocol."""
        return writer

    @provide
    def instrument_store_protocol(
        self,
        reader: InstrumentReader,
    ) -> InstrumentStoreProtocol:
        """InstrumentReader → InstrumentStoreProtocol."""
        return reader

    @provide
    def compile_cache_backend(
        self,
        client: SQLiteClient,
    ) -> SQLiteCompileCacheBackend:
        """SQLiteClient → SQLiteCompileCacheBackend."""
        return client

    @provide
    def source_data_port(self, accessor: SourceAccessor) -> SourceDataPort:
        """SourceAccessor.tushare → SourceDataPort."""
        return accessor.tushare

    @provide
    def catalog_remediation_ingest_date_port(
        self,
    ) -> CatalogRemediationIngestDatePort:
        """Remediation source-coverage executor → source=auto ingestion bundle."""
        return cast(
            CatalogRemediationIngestDatePort,
            _CatalogRemediationIngestDateAdapter(),
        )
