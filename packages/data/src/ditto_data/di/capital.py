"""Data 层 - Capital Domain Provider。"""

from __future__ import annotations

from dishka import Provider, Scope, provide

from ditto_data.services.capital_service import CapitalService
from ditto_data.services.deps import CapitalReaders, CapitalWriters
from ditto_data.storage.capital.index_composition.index_composition_reader import (
    IndexCompositionReader,
)
from ditto_data.storage.capital.index_composition.index_composition_writer import (
    IndexCompositionWriter,
)
from ditto_data.storage.capital.margin.margin_trading_reader import (
    MarginTradingReader,
)
from ditto_data.storage.capital.margin.margin_trading_writer import (
    MarginTradingWriter,
)
from ditto_data.storage.capital.pledge.pledge_ratio_reader import (
    PledgeRatioReader,
)
from ditto_data.storage.capital.pledge.pledge_ratio_writer import (
    PledgeRatioWriter,
)
from ditto_data.storage.capital.specs import (
    INDEX_COMPOSITION_SPEC,
    MARGIN_TRADING_SPEC,
    PLEDGE_RATIO_SPEC,
    VALUATION_METRICS_SPEC,
)
from ditto_data.storage.capital.valuation.valuation_metrics_reader import (
    ValuationMetricsReader,
)
from ditto_data.storage.capital.valuation.valuation_metrics_writer import (
    ValuationMetricsWriter,
)
from ditto_data.storage.sqlite_client import SQLiteClient

__all__ = ["CapitalProvider"]


class CapitalProvider(Provider):
    """Capital Domain Provider - 融资融券、质押、估值、指数成分."""

    scope = Scope.APP

    @provide
    def index_composition_reader(
        self,
        sqlite_client: SQLiteClient,
    ) -> IndexCompositionReader:
        """IndexComposition reader (MetadataService/UniverseService 直接依赖)."""
        return IndexCompositionReader(INDEX_COMPOSITION_SPEC, sqlite_client)

    @provide
    def capital_readers(self, sqlite_client: SQLiteClient) -> CapitalReaders:
        """Capital 域读取依赖聚合。"""
        return CapitalReaders(
            margin_trading=MarginTradingReader(MARGIN_TRADING_SPEC, sqlite_client),
            pledge_ratio=PledgeRatioReader(PLEDGE_RATIO_SPEC, sqlite_client),
            valuation_metrics=ValuationMetricsReader(
                VALUATION_METRICS_SPEC,
                sqlite_client,
            ),
            index_composition=IndexCompositionReader(
                INDEX_COMPOSITION_SPEC,
                sqlite_client,
            ),
        )

    @provide
    def capital_writers(self, sqlite_client: SQLiteClient) -> CapitalWriters:
        """Capital 域写入依赖聚合。"""
        return CapitalWriters(
            margin_trading=MarginTradingWriter(MARGIN_TRADING_SPEC, sqlite_client),
            pledge_ratio=PledgeRatioWriter(PLEDGE_RATIO_SPEC, sqlite_client),
            valuation_metrics=ValuationMetricsWriter(
                VALUATION_METRICS_SPEC,
                sqlite_client,
            ),
            index_composition=IndexCompositionWriter(
                INDEX_COMPOSITION_SPEC,
                sqlite_client,
            ),
        )

    @provide
    def capital_service(
        self,
        capital_read_ports: CapitalReaders,
        capital_write_ports: CapitalWriters,
    ) -> CapitalService:
        """Capital domain unified service."""
        return CapitalService(
            read_ports=capital_read_ports,
            write_ports=capital_write_ports,
        )
