"""Data 层 - Fundamental Domain Provider。"""

from __future__ import annotations

from dishka import Provider, Scope, provide
from ditto_platform.foundation import SQLiteClient

from ditto_data.services.deps import FundamentalReaders, FundamentalWriters
from ditto_data.services.fundamental_service import FundamentalService
from ditto_data.storage.fundamental.corporate.corporate_actions_reader import (
    CorporateActionsReader,
)
from ditto_data.storage.fundamental.corporate.corporate_actions_writer import (
    CorporateActionsWriter,
)
from ditto_data.storage.fundamental.corporate.dividend_reader import (
    DividendReader,
)
from ditto_data.storage.fundamental.corporate.dividend_writer import (
    DividendWriter,
)
from ditto_data.storage.fundamental.financial.balance_sheet_reader import (
    BalanceSheetReader,
)
from ditto_data.storage.fundamental.financial.balance_sheet_writer import (
    BalanceSheetWriter,
)
from ditto_data.storage.fundamental.financial.cash_flow_reader import (
    CashFlowReader,
)
from ditto_data.storage.fundamental.financial.cash_flow_writer import (
    CashFlowWriter,
)
from ditto_data.storage.fundamental.financial.income_statement_reader import (
    IncomeStatementReader,
)
from ditto_data.storage.fundamental.financial.income_statement_writer import (
    IncomeStatementWriter,
)
from ditto_data.storage.fundamental.forecast.express_reader import (
    ExpressReader,
)
from ditto_data.storage.fundamental.forecast.express_writer import (
    ExpressWriter,
)
from ditto_data.storage.fundamental.forecast.forecast_reader import (
    ForecastReader,
)
from ditto_data.storage.fundamental.forecast.forecast_writer import (
    ForecastWriter,
)
from ditto_data.storage.fundamental.specs import (
    BALANCE_SHEET_SPEC,
    CASH_FLOW_SPEC,
    CORPORATE_ACTIONS_SPEC,
    DIVIDEND_SPEC,
    EXPRESS_SPEC,
    FORECAST_SPEC,
    INCOME_STATEMENT_SPEC,
)

__all__ = ["FundamentalProvider"]


class FundamentalProvider(Provider):
    """Fundamental Domain Provider - 财务报表、股息、公司行动、业绩预告."""

    scope = Scope.APP

    @provide
    def fundamental_readers(self, sqlite_client: SQLiteClient) -> FundamentalReaders:
        """Fundamental 域读取依赖聚合。"""
        return FundamentalReaders(
            balance_sheet=BalanceSheetReader(BALANCE_SHEET_SPEC, sqlite_client),
            income_statement=IncomeStatementReader(
                INCOME_STATEMENT_SPEC,
                sqlite_client,
            ),
            cash_flow=CashFlowReader(CASH_FLOW_SPEC, sqlite_client),
            dividend=DividendReader(DIVIDEND_SPEC, sqlite_client),
            corporate_actions=CorporateActionsReader(
                CORPORATE_ACTIONS_SPEC,
                sqlite_client,
            ),
            forecast=ForecastReader(FORECAST_SPEC, sqlite_client),
            express=ExpressReader(EXPRESS_SPEC, sqlite_client),
        )

    @provide
    def fundamental_writers(self, sqlite_client: SQLiteClient) -> FundamentalWriters:
        """Fundamental 域写入依赖聚合。"""
        return FundamentalWriters(
            balance_sheet=BalanceSheetWriter(BALANCE_SHEET_SPEC, sqlite_client),
            income_statement=IncomeStatementWriter(
                INCOME_STATEMENT_SPEC,
                sqlite_client,
            ),
            cash_flow=CashFlowWriter(CASH_FLOW_SPEC, sqlite_client),
            dividend=DividendWriter(DIVIDEND_SPEC, sqlite_client),
            corporate_actions=CorporateActionsWriter(
                CORPORATE_ACTIONS_SPEC,
                sqlite_client,
            ),
            forecast=ForecastWriter(FORECAST_SPEC, sqlite_client),
            express=ExpressWriter(EXPRESS_SPEC, sqlite_client),
        )

    @provide
    def fundamental_service(
        self,
        read_ports: FundamentalReaders,
        write_ports: FundamentalWriters,
    ) -> FundamentalService:
        """Fundamental domain unified service."""
        return FundamentalService(
            read_ports=read_ports,
            write_ports=write_ports,
        )
