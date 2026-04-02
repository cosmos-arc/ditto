"""DataHub 层 - Fundamental Domain Provider。"""

from __future__ import annotations

from dishka import Provider, Scope, provide
from ditto_data.services.fundamental_service import FundamentalService
from ditto_data.services.ports import FundamentalReadPorts, FundamentalWritePorts
from ditto_data.stores.fundamental.corporate.corporate_actions_reader import (
    CorporateActionsReader,
)
from ditto_data.stores.fundamental.corporate.corporate_actions_writer import (
    CorporateActionsWriter,
)
from ditto_data.stores.fundamental.corporate.dividend_reader import (
    DividendReader,
)
from ditto_data.stores.fundamental.corporate.dividend_writer import (
    DividendWriter,
)
from ditto_data.stores.fundamental.financial.balance_sheet_reader import (
    BalanceSheetReader,
)
from ditto_data.stores.fundamental.financial.balance_sheet_writer import (
    BalanceSheetWriter,
)
from ditto_data.stores.fundamental.financial.cash_flow_reader import (
    CashFlowReader,
)
from ditto_data.stores.fundamental.financial.cash_flow_writer import (
    CashFlowWriter,
)
from ditto_data.stores.fundamental.financial.income_statement_reader import (
    IncomeStatementReader,
)
from ditto_data.stores.fundamental.financial.income_statement_writer import (
    IncomeStatementWriter,
)
from ditto_data.stores.fundamental.forecast.express_reader import (
    ExpressReader,
)
from ditto_data.stores.fundamental.forecast.express_writer import (
    ExpressWriter,
)
from ditto_data.stores.fundamental.forecast.forecast_reader import (
    ForecastReader,
)
from ditto_data.stores.fundamental.forecast.forecast_writer import (
    ForecastWriter,
)
from ditto_data.stores.sqlite_client import SQLiteClient

from .builders import sqlite_store_pair

__all__ = ["FundamentalProvider"]

# ============================================================================
# SQLite Store 工厂函数（减少样板代码）
# ============================================================================

# Financial Statements
_balance_r, _balance_w = sqlite_store_pair(BalanceSheetReader, BalanceSheetWriter)
_income_r, _income_w = sqlite_store_pair(IncomeStatementReader, IncomeStatementWriter)
_cashflow_r, _cashflow_w = sqlite_store_pair(CashFlowReader, CashFlowWriter)

# Corporate Actions
_dividend_r, _dividend_w = sqlite_store_pair(DividendReader, DividendWriter)
_corp_actions_r, _corp_actions_w = sqlite_store_pair(
    CorporateActionsReader, CorporateActionsWriter
)

# Forecast
_forecast_r, _forecast_w = sqlite_store_pair(ForecastReader, ForecastWriter)
_express_r, _express_w = sqlite_store_pair(ExpressReader, ExpressWriter)


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
        return _balance_r(sqlite_client)

    @provide
    def balance_sheet_writer(
        self,
        sqlite_client: SQLiteClient,
    ) -> BalanceSheetWriter:
        """BalanceSheet writer."""
        return _balance_w(sqlite_client)

    @provide
    def income_statement_reader(
        self,
        sqlite_client: SQLiteClient,
    ) -> IncomeStatementReader:
        """IncomeStatement reader."""
        return _income_r(sqlite_client)

    @provide
    def income_statement_writer(
        self,
        sqlite_client: SQLiteClient,
    ) -> IncomeStatementWriter:
        """IncomeStatement writer."""
        return _income_w(sqlite_client)

    @provide
    def cash_flow_reader(
        self,
        sqlite_client: SQLiteClient,
    ) -> CashFlowReader:
        """CashFlow reader."""
        return _cashflow_r(sqlite_client)

    @provide
    def cash_flow_writer(
        self,
        sqlite_client: SQLiteClient,
    ) -> CashFlowWriter:
        """CashFlow writer."""
        return _cashflow_w(sqlite_client)

    # ========================================================================
    # Corporate Actions Stores
    # ========================================================================

    @provide
    def dividend_reader(
        self,
        sqlite_client: SQLiteClient,
    ) -> DividendReader:
        """Dividend reader."""
        return _dividend_r(sqlite_client)

    @provide
    def dividend_writer(
        self,
        sqlite_client: SQLiteClient,
    ) -> DividendWriter:
        """Dividend writer."""
        return _dividend_w(sqlite_client)

    @provide
    def corporate_actions_reader(
        self,
        sqlite_client: SQLiteClient,
    ) -> CorporateActionsReader:
        """CorporateActions reader."""
        return _corp_actions_r(sqlite_client)

    @provide
    def corporate_actions_writer(
        self,
        sqlite_client: SQLiteClient,
    ) -> CorporateActionsWriter:
        """CorporateActions writer."""
        return _corp_actions_w(sqlite_client)

    # ========================================================================
    # Forecast Stores
    # ========================================================================

    @provide
    def forecast_reader(
        self,
        sqlite_client: SQLiteClient,
    ) -> ForecastReader:
        """Forecast reader."""
        return _forecast_r(sqlite_client)

    @provide
    def forecast_writer(
        self,
        sqlite_client: SQLiteClient,
    ) -> ForecastWriter:
        """Forecast writer."""
        return _forecast_w(sqlite_client)

    @provide
    def express_reader(
        self,
        sqlite_client: SQLiteClient,
    ) -> ExpressReader:
        """Express reader."""
        return _express_r(sqlite_client)

    @provide
    def express_writer(
        self,
        sqlite_client: SQLiteClient,
    ) -> ExpressWriter:
        """Express writer."""
        return _express_w(sqlite_client)

    # ========================================================================
    # Fundamental Ports
    # ========================================================================

    @provide
    def fundamental_read_ports(
        self,
        balance_sheet_reader: BalanceSheetReader,
        income_statement_reader: IncomeStatementReader,
        cash_flow_reader: CashFlowReader,
        dividend_reader: DividendReader,
        corporate_actions_reader: CorporateActionsReader,
        forecast_reader: ForecastReader,
        express_reader: ExpressReader,
    ) -> FundamentalReadPorts:
        """Fundamental 域读取端口."""
        return FundamentalReadPorts(
            balance_sheet=balance_sheet_reader,
            income_statement=income_statement_reader,
            cash_flow=cash_flow_reader,
            dividend=dividend_reader,
            corporate_actions=corporate_actions_reader,
            forecast=forecast_reader,
            express=express_reader,
        )

    @provide
    def fundamental_write_ports(
        self,
        balance_sheet_writer: BalanceSheetWriter,
        income_statement_writer: IncomeStatementWriter,
        cash_flow_writer: CashFlowWriter,
        dividend_writer: DividendWriter,
        corporate_actions_writer: CorporateActionsWriter,
        forecast_writer: ForecastWriter,
        express_writer: ExpressWriter,
    ) -> FundamentalWritePorts:
        """Fundamental 域写入端口."""
        return FundamentalWritePorts(
            balance_sheet=balance_sheet_writer,
            income_statement=income_statement_writer,
            cash_flow=cash_flow_writer,
            dividend=dividend_writer,
            corporate_actions=corporate_actions_writer,
            forecast=forecast_writer,
            express=express_writer,
        )

    # ========================================================================
    # Fundamental Service
    # ========================================================================

    @provide
    def fundamental_service(
        self,
        read_ports: FundamentalReadPorts,
        write_ports: FundamentalWritePorts,
    ) -> FundamentalService:
        """Fundamental domain unified service."""
        return FundamentalService(
            read_ports=read_ports,
            write_ports=write_ports,
        )
