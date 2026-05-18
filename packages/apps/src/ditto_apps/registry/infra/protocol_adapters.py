"""
Protocol adapters — bridge concrete infrastructure types to Protocol interfaces.

Composition root responsibility: concrete types live in data/platform/features DI;
application providers only depend on Protocol interfaces.  This module closes the
gap so Dishka can resolve Protocol-typed parameters without structural subtyping.
"""

from __future__ import annotations

from dishka import Provider, Scope, provide
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
        """TushareSource → SourceDataPort."""
        return accessor.tushare
