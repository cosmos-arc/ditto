"""DataHub 层 - Capital Domain Provider。"""

from __future__ import annotations

from dishka import Provider, Scope, provide
from ditto_data.services.capital_service import CapitalService
from ditto_data.services.ports import CapitalReadPorts, CapitalWritePorts
from ditto_data.stores.capital.index_composition.index_composition_reader import (
    IndexCompositionReader,
)
from ditto_data.stores.capital.index_composition.index_composition_writer import (
    IndexCompositionWriter,
)
from ditto_data.stores.capital.margin.margin_trading_reader import (
    MarginTradingReader,
)
from ditto_data.stores.capital.margin.margin_trading_writer import (
    MarginTradingWriter,
)
from ditto_data.stores.capital.pledge.pledge_ratio_reader import (
    PledgeRatioReader,
)
from ditto_data.stores.capital.pledge.pledge_ratio_writer import (
    PledgeRatioWriter,
)
from ditto_data.stores.capital.valuation.valuation_metrics_reader import (
    ValuationMetricsReader,
)
from ditto_data.stores.capital.valuation.valuation_metrics_writer import (
    ValuationMetricsWriter,
)
from ditto_data.stores.sqlite_client import SQLiteClient

from .builders import sqlite_store_pair

__all__ = ["CapitalProvider"]

# ============================================================================
# SQLite Store 工厂函数（减少样板代码）
# ============================================================================

# Margin Trading
_margin_r, _margin_w = sqlite_store_pair(MarginTradingReader, MarginTradingWriter)

# Pledge
_pledge_r, _pledge_w = sqlite_store_pair(PledgeRatioReader, PledgeRatioWriter)

# Valuation
_valuation_r, _valuation_w = sqlite_store_pair(
    ValuationMetricsReader, ValuationMetricsWriter
)

# Index Composition
_index_comp_r, _index_comp_w = sqlite_store_pair(
    IndexCompositionReader, IndexCompositionWriter
)


class CapitalProvider(Provider):
    """Capital Domain Provider - 融资融券、质押、估值、指数成分."""

    scope = Scope.APP

    # ========================================================================
    # Margin Trading Stores
    # ========================================================================

    @provide
    def margin_trading_reader(
        self,
        sqlite_client: SQLiteClient,
    ) -> MarginTradingReader:
        """MarginTrading reader."""
        return _margin_r(sqlite_client)

    @provide
    def margin_trading_writer(
        self,
        sqlite_client: SQLiteClient,
    ) -> MarginTradingWriter:
        """MarginTrading writer."""
        return _margin_w(sqlite_client)

    # ========================================================================
    # Pledge Stores
    # ========================================================================

    @provide
    def pledge_ratio_reader(
        self,
        sqlite_client: SQLiteClient,
    ) -> PledgeRatioReader:
        """PledgeRatio reader."""
        return _pledge_r(sqlite_client)

    @provide
    def pledge_ratio_writer(
        self,
        sqlite_client: SQLiteClient,
    ) -> PledgeRatioWriter:
        """PledgeRatio writer."""
        return _pledge_w(sqlite_client)

    # ========================================================================
    # Valuation Stores
    # ========================================================================

    @provide
    def valuation_metrics_reader(
        self,
        sqlite_client: SQLiteClient,
    ) -> ValuationMetricsReader:
        """ValuationMetrics reader."""
        return _valuation_r(sqlite_client)

    @provide
    def valuation_metrics_writer(
        self,
        sqlite_client: SQLiteClient,
    ) -> ValuationMetricsWriter:
        """ValuationMetrics writer."""
        return _valuation_w(sqlite_client)

    # ========================================================================
    # Index Composition Stores
    # ========================================================================

    @provide
    def index_composition_reader(
        self,
        sqlite_client: SQLiteClient,
    ) -> IndexCompositionReader:
        """IndexComposition reader."""
        return _index_comp_r(sqlite_client)

    @provide
    def index_composition_writer(
        self,
        sqlite_client: SQLiteClient,
    ) -> IndexCompositionWriter:
        """IndexComposition writer."""
        return _index_comp_w(sqlite_client)

    # ========================================================================
    # Capital Ports
    # ========================================================================

    @provide
    def capital_read_ports(
        self,
        margin_trading_reader: MarginTradingReader,
        pledge_ratio_reader: PledgeRatioReader,
        valuation_metrics_reader: ValuationMetricsReader,
        index_composition_reader: IndexCompositionReader,
    ) -> CapitalReadPorts:
        """Capital domain read ports."""
        return CapitalReadPorts(
            margin_trading=margin_trading_reader,
            pledge_ratio=pledge_ratio_reader,
            valuation_metrics=valuation_metrics_reader,
            index_composition=index_composition_reader,
        )

    @provide
    def capital_write_ports(
        self,
        margin_trading_writer: MarginTradingWriter,
        pledge_ratio_writer: PledgeRatioWriter,
        valuation_metrics_writer: ValuationMetricsWriter,
        index_composition_writer: IndexCompositionWriter,
    ) -> CapitalWritePorts:
        """Capital domain write ports."""
        return CapitalWritePorts(
            margin_trading=margin_trading_writer,
            pledge_ratio=pledge_ratio_writer,
            valuation_metrics=valuation_metrics_writer,
            index_composition=index_composition_writer,
        )

    # ========================================================================
    # Capital Service
    # ========================================================================

    @provide
    def capital_service(
        self,
        capital_read_ports: CapitalReadPorts,
        capital_write_ports: CapitalWritePorts,
    ) -> CapitalService:
        """Capital domain unified service."""
        return CapitalService(
            read_ports=capital_read_ports,
            write_ports=capital_write_ports,
        )
