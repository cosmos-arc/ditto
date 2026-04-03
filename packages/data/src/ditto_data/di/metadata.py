"""DataHub 层 - Metadata Domain Provider。"""

from __future__ import annotations

from typing import Any

from dishka import Provider, Scope, provide
from ditto_infra.foundation.cache import DataCache

from ditto_data.runtime.instrument_id_allocator import InstrumentIdAllocator
from ditto_data.services.metadata_service import MetadataService
from ditto_data.sources import ExchangeTransformers
from ditto_data.storage.capital.index_composition import IndexCompositionReader
from ditto_data.storage.metadata.calendar import CalendarReader, CalendarWriter
from ditto_data.storage.metadata.industry import (
    IndustryMappingReader,
    IndustryMappingWriter,
    IndustryReader,
    IndustryWriter,
)
from ditto_data.storage.metadata.instrument import (
    InstrumentReader,
    InstrumentWriter,
    NameHistoryReader,
    NameHistoryWriter,
)
from ditto_data.storage.metadata.universe import (
    RebalanceReader,
    RebalanceWriter,
    UniverseReader,
    UniverseWriter,
)
from ditto_data.storage.sqlite_client import SQLiteClient

__all__ = ["MetadataProvider"]


class MetadataProvider(Provider):
    """Metadata Domain Provider - 证券主数据、日历、行业、标的池."""

    scope = Scope.APP

    # ========================================================================
    # Instrument Store
    # ========================================================================

    @provide
    def instrument_reader(
        self,
        sqlite_client: SQLiteClient,
    ) -> InstrumentReader:
        """证券数据读取器."""
        return InstrumentReader(sqlite_client)

    @provide
    def instrument_writer(
        self,
        sqlite_client: SQLiteClient,
        data_cache: DataCache[Any],
    ) -> InstrumentWriter:
        """证券主数据写入器."""
        return InstrumentWriter(client=sqlite_client, cache=data_cache)

    @provide
    def name_history_reader(
        self,
        sqlite_client: SQLiteClient,
        data_cache: DataCache[Any],
    ) -> NameHistoryReader:
        """证券名称变更历史读取器."""
        return NameHistoryReader(client=sqlite_client, cache=data_cache)

    @provide
    def name_history_writer(
        self,
        sqlite_client: SQLiteClient,
        data_cache: DataCache[Any],
    ) -> NameHistoryWriter:
        """证券名称变更历史写入器."""
        return NameHistoryWriter(client=sqlite_client, cache=data_cache)

    # ========================================================================
    # Calendar Store
    # ========================================================================

    @provide
    def calendar_reader(self, sqlite_client: SQLiteClient) -> CalendarReader:
        """交易日历读取器."""
        return CalendarReader(sqlite_client)

    @provide
    def calendar_writer(
        self,
        sqlite_client: SQLiteClient,
        data_cache: DataCache[Any],
        calendar_reader: CalendarReader,
    ) -> CalendarWriter:
        """交易日历写入器."""
        return CalendarWriter(
            sqlite_client=sqlite_client,
            data_cache=data_cache,
            reader=calendar_reader,
        )

    # ========================================================================
    # Industry Store
    # ========================================================================

    @provide
    def industry_reader(
        self,
        sqlite_client: SQLiteClient,
        data_cache: DataCache[Any],
    ) -> IndustryReader:
        """行业主数据读取器."""
        return IndustryReader(client=sqlite_client, cache=data_cache)

    @provide
    def industry_writer(
        self,
        sqlite_client: SQLiteClient,
        data_cache: DataCache[Any],
    ) -> IndustryWriter:
        """行业主数据写入器."""
        return IndustryWriter(client=sqlite_client, cache=data_cache)

    @provide
    def industry_mapping_reader(
        self,
        sqlite_client: SQLiteClient,
        data_cache: DataCache[Any],
    ) -> IndustryMappingReader:
        """行业映射读取器."""
        return IndustryMappingReader(client=sqlite_client, cache=data_cache)

    @provide
    def industry_mapping_writer(
        self,
        sqlite_client: SQLiteClient,
        data_cache: DataCache[Any],
    ) -> IndustryMappingWriter:
        """行业映射写入器."""
        return IndustryMappingWriter(client=sqlite_client, cache=data_cache)

    # ========================================================================
    # Universe Store
    # ========================================================================

    @provide
    def universe_reader(
        self,
        sqlite_client: SQLiteClient,
        data_cache: DataCache[Any],
    ) -> UniverseReader:
        """标的池读取器."""
        return UniverseReader(client=sqlite_client, cache=data_cache)

    @provide
    def universe_writer(
        self,
        sqlite_client: SQLiteClient,
        data_cache: DataCache[Any],
    ) -> UniverseWriter:
        """标的池写入器."""
        return UniverseWriter(client=sqlite_client, cache=data_cache)

    @provide
    def rebalance_reader(
        self,
        sqlite_client: SQLiteClient,
        data_cache: DataCache[Any],
    ) -> RebalanceReader:
        """标的池调仓日程读取器."""
        return RebalanceReader(client=sqlite_client, cache=data_cache)

    @provide
    def rebalance_writer(
        self,
        sqlite_client: SQLiteClient,
        data_cache: DataCache[Any],
    ) -> RebalanceWriter:
        """标的池调仓日程写入器."""
        return RebalanceWriter(client=sqlite_client, cache=data_cache)

    # ========================================================================
    # Metadata Service
    # ========================================================================

    @provide
    def metadata_service(  # noqa: PLR0913
        self,
        instrument_reader: InstrumentReader,
        instrument_writer: InstrumentWriter,
        name_history_reader: NameHistoryReader,
        name_history_writer: NameHistoryWriter,
        calendar_reader: CalendarReader,
        calendar_writer: CalendarWriter,
        industry_reader: IndustryReader,
        industry_writer: IndustryWriter,
        industry_mapping_reader: IndustryMappingReader,
        industry_mapping_writer: IndustryMappingWriter,
        universe_reader: UniverseReader,
        universe_writer: UniverseWriter,
        rebalance_reader: RebalanceReader,
        rebalance_writer: RebalanceWriter,
        instrument_id_allocator: InstrumentIdAllocator,
        index_composition_reader: IndexCompositionReader,
        exchange_transformers: ExchangeTransformers,
    ) -> MetadataService:
        """Metadata 查询服务（CQRS Reader/Writer）。"""
        return MetadataService(
            instrument_reader=instrument_reader,
            instrument_writer=instrument_writer,
            name_history_reader=name_history_reader,
            name_history_writer=name_history_writer,
            calendar_reader=calendar_reader,
            calendar_writer=calendar_writer,
            industry_reader=industry_reader,
            industry_writer=industry_writer,
            industry_mapping_reader=industry_mapping_reader,
            industry_mapping_writer=industry_mapping_writer,
            universe_reader=universe_reader,
            universe_writer=universe_writer,
            rebalance_reader=rebalance_reader,
            rebalance_writer=rebalance_writer,
            instrument_id_allocator=instrument_id_allocator,
            index_composition_reader=index_composition_reader,
            exchange_transformers=exchange_transformers,
        )
