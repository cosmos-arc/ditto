"""DataHub 层 - Fundamental Domain Provider。"""

from __future__ import annotations

from dishka import Provider, Scope, provide
from ditto_datahub.services.fundamental_service import FundamentalService
from ditto_datahub.stores.fundamental.corporate.corporate_actions_reader import (
    CorporateActionsReader,
)
from ditto_datahub.stores.fundamental.corporate.corporate_actions_writer import (
    CorporateActionsWriter,
)
from ditto_datahub.stores.fundamental.corporate.dividend_reader import (
    DividendReader,
)
from ditto_datahub.stores.fundamental.corporate.dividend_writer import (
    DividendWriter,
)
from ditto_datahub.stores.fundamental.financial.balance_sheet_reader import (
    BalanceSheetReader,
)
from ditto_datahub.stores.fundamental.financial.balance_sheet_writer import (
    BalanceSheetWriter,
)
from ditto_datahub.stores.fundamental.financial.cash_flow_reader import (
    CashFlowReader,
)
from ditto_datahub.stores.fundamental.financial.cash_flow_writer import (
    CashFlowWriter,
)
from ditto_datahub.stores.fundamental.financial.income_statement_reader import (
    IncomeStatementReader,
)
from ditto_datahub.stores.fundamental.financial.income_statement_writer import (
    IncomeStatementWriter,
)
from ditto_datahub.stores.fundamental.forecast.express_reader import (
    ExpressReader,
)
from ditto_datahub.stores.fundamental.forecast.express_writer import (
    ExpressWriter,
)
from ditto_datahub.stores.fundamental.forecast.forecast_reader import (
    ForecastReader,
)
from ditto_datahub.stores.fundamental.forecast.forecast_writer import (
    ForecastWriter,
)
from ditto_datahub.stores.sqlite_client import SQLiteClient

__all__ = ["FundamentalProvider"]


class FundamentalProvider(Provider):
    """Fundamental Domain Provider - 财务报表、股息、公司行动、业绩预告."""

    scope = Scope.APP

    # ========================================================================
    # Financial Statements Stores
    # ========================================================================

    @provide
    def balance_sheet_reader(
        self,
        sqlite_client: SQLiteClient,
    ) -> BalanceSheetReader:
        """BalanceSheet reader."""
        return BalanceSheetReader(sqlite_client)

    @provide
    def balance_sheet_writer(
        self,
        sqlite_client: SQLiteClient,
    ) -> BalanceSheetWriter:
        """BalanceSheet writer."""
        return BalanceSheetWriter(sqlite_client)

    @provide
    def income_statement_reader(
        self,
        sqlite_client: SQLiteClient,
    ) -> IncomeStatementReader:
        """IncomeStatement reader."""
        return IncomeStatementReader(sqlite_client)

    @provide
    def income_statement_writer(
        self,
        sqlite_client: SQLiteClient,
    ) -> IncomeStatementWriter:
        """IncomeStatement writer."""
        return IncomeStatementWriter(sqlite_client)

    @provide
    def cash_flow_reader(
        self,
        sqlite_client: SQLiteClient,
    ) -> CashFlowReader:
        """CashFlow reader."""
        return CashFlowReader(sqlite_client)

    @provide
    def cash_flow_writer(
        self,
        sqlite_client: SQLiteClient,
    ) -> CashFlowWriter:
        """CashFlow writer."""
        return CashFlowWriter(sqlite_client)

    # ========================================================================
    # Corporate Actions Stores
    # ========================================================================

    @provide
    def dividend_reader(
        self,
        sqlite_client: SQLiteClient,
    ) -> DividendReader:
        """Dividend reader."""
        return DividendReader(sqlite_client)

    @provide
    def dividend_writer(
        self,
        sqlite_client: SQLiteClient,
    ) -> DividendWriter:
        """Dividend writer."""
        return DividendWriter(sqlite_client)

    @provide
    def corporate_actions_reader(
        self,
        sqlite_client: SQLiteClient,
    ) -> CorporateActionsReader:
        """CorporateActions reader."""
        return CorporateActionsReader(sqlite_client)

    @provide
    def corporate_actions_writer(
        self,
        sqlite_client: SQLiteClient,
    ) -> CorporateActionsWriter:
        """CorporateActions writer."""
        return CorporateActionsWriter(sqlite_client)

    # ========================================================================
    # Forecast Stores
    # ========================================================================

    @provide
    def forecast_reader(
        self,
        sqlite_client: SQLiteClient,
    ) -> ForecastReader:
        """Forecast reader."""
        return ForecastReader(sqlite_client)

    @provide
    def forecast_writer(
        self,
        sqlite_client: SQLiteClient,
    ) -> ForecastWriter:
        """Forecast writer."""
        return ForecastWriter(sqlite_client)

    @provide
    def express_reader(
        self,
        sqlite_client: SQLiteClient,
    ) -> ExpressReader:
        """Express reader."""
        return ExpressReader(sqlite_client)

    @provide
    def express_writer(
        self,
        sqlite_client: SQLiteClient,
    ) -> ExpressWriter:
        """Express writer."""
        return ExpressWriter(sqlite_client)

    # ========================================================================
    # Fundamental Service
    # ========================================================================

    @provide
    def fundamental_service(  # noqa: PLR0913
        self,
        balance_sheet_reader: BalanceSheetReader,
        balance_sheet_writer: BalanceSheetWriter,
        income_statement_reader: IncomeStatementReader,
        income_statement_writer: IncomeStatementWriter,
        cash_flow_reader: CashFlowReader,
        cash_flow_writer: CashFlowWriter,
        dividend_reader: DividendReader,
        dividend_writer: DividendWriter,
        corporate_actions_reader: CorporateActionsReader,
        corporate_actions_writer: CorporateActionsWriter,
        forecast_reader: ForecastReader,
        forecast_writer: ForecastWriter,
        express_reader: ExpressReader,
        express_writer: ExpressWriter,
    ) -> FundamentalService:
        """Fundamental domain unified service."""
        return FundamentalService(
            balance_sheet_reader=balance_sheet_reader,
            balance_sheet_writer=balance_sheet_writer,
            income_statement_reader=income_statement_reader,
            income_statement_writer=income_statement_writer,
            cash_flow_reader=cash_flow_reader,
            cash_flow_writer=cash_flow_writer,
            dividend_reader=dividend_reader,
            dividend_writer=dividend_writer,
            corporate_actions_reader=corporate_actions_reader,
            corporate_actions_writer=corporate_actions_writer,
            forecast_reader=forecast_reader,
            forecast_writer=forecast_writer,
            express_reader=express_reader,
            express_writer=express_writer,
        )
