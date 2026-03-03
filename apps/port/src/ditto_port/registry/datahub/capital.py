"""DataHub 层 - Capital Domain Provider。"""

from __future__ import annotations

from dishka import Provider, Scope, provide
from ditto_datahub.services.capital_service import CapitalService
from ditto_datahub.services.ports import CapitalReadPorts, CapitalWritePorts
from ditto_datahub.stores.capital.index_composition.index_composition_reader import (
    IndexCompositionReader,
)
from ditto_datahub.stores.capital.index_composition.index_composition_writer import (
    IndexCompositionWriter,
)
from ditto_datahub.stores.capital.margin.margin_trading_reader import (
    MarginTradingReader,
)
from ditto_datahub.stores.capital.margin.margin_trading_writer import (
    MarginTradingWriter,
)
from ditto_datahub.stores.capital.pledge.pledge_ratio_reader import (
    PledgeRatioReader,
)
from ditto_datahub.stores.capital.pledge.pledge_ratio_writer import (
    PledgeRatioWriter,
)
from ditto_datahub.stores.capital.valuation.valuation_metrics_reader import (
    ValuationMetricsReader,
)
from ditto_datahub.stores.capital.valuation.valuation_metrics_writer import (
    ValuationMetricsWriter,
)
from ditto_datahub.stores.sqlite_client import SQLiteClient

__all__ = ["CapitalProvider"]


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
        return MarginTradingReader(client=sqlite_client)

    @provide
    def margin_trading_writer(
        self,
        sqlite_client: SQLiteClient,
    ) -> MarginTradingWriter:
        """MarginTrading writer."""
        return MarginTradingWriter(client=sqlite_client)

    # ========================================================================
    # Pledge Stores
    # ========================================================================

    @provide
    def pledge_ratio_reader(
        self,
        sqlite_client: SQLiteClient,
    ) -> PledgeRatioReader:
        """PledgeRatio reader."""
        return PledgeRatioReader(client=sqlite_client)

    @provide
    def pledge_ratio_writer(
        self,
        sqlite_client: SQLiteClient,
    ) -> PledgeRatioWriter:
        """PledgeRatio writer."""
        return PledgeRatioWriter(client=sqlite_client)

    # ========================================================================
    # Valuation Stores
    # ========================================================================

    @provide
    def valuation_metrics_reader(
        self,
        sqlite_client: SQLiteClient,
    ) -> ValuationMetricsReader:
        """ValuationMetrics reader."""
        return ValuationMetricsReader(client=sqlite_client)

    @provide
    def valuation_metrics_writer(
        self,
        sqlite_client: SQLiteClient,
    ) -> ValuationMetricsWriter:
        """ValuationMetrics writer."""
        return ValuationMetricsWriter(client=sqlite_client)

    # ========================================================================
    # Index Composition Stores
    # ========================================================================

    @provide
    def index_composition_reader(
        self,
        sqlite_client: SQLiteClient,
    ) -> IndexCompositionReader:
        """IndexComposition reader."""
        return IndexCompositionReader(client=sqlite_client)

    @provide
    def index_composition_writer(
        self,
        sqlite_client: SQLiteClient,
    ) -> IndexCompositionWriter:
        """IndexComposition writer."""
        return IndexCompositionWriter(client=sqlite_client)

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
