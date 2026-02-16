"""Fundamental domain service with dedicated get/save methods."""

from __future__ import annotations

from datetime import date

import polars as pl
from ditto_infra.foundation import logger

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


class FundamentalService:
    """
    Fundamental domain unified service.

    Thin wrapper with dependency injection using CQRS pattern.
    Delegates read operations to Readers and write operations to Writers.
    """

    def __init__(  # noqa: PLR0913
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
    ) -> None:
        """
        Initialize FundamentalService with CQRS Readers and Writers.

        Args:
            balance_sheet_reader: BalanceSheet data reader.
            balance_sheet_writer: BalanceSheet data writer.
            income_statement_reader: IncomeStatement data reader.
            income_statement_writer: IncomeStatement data writer.
            cash_flow_reader: CashFlow data reader.
            cash_flow_writer: CashFlow data writer.
            dividend_reader: Dividend data reader.
            dividend_writer: Dividend data writer.
            corporate_actions_reader: CorporateActions data reader.
            corporate_actions_writer: CorporateActions data writer.
            forecast_reader: Forecast data reader.
            forecast_writer: Forecast data writer.
            express_reader: Express data reader.
            express_writer: Express data writer.

        """
        self._balance_sheet_reader = balance_sheet_reader
        self._balance_sheet_writer = balance_sheet_writer
        self._income_statement_reader = income_statement_reader
        self._income_statement_writer = income_statement_writer
        self._cash_flow_reader = cash_flow_reader
        self._cash_flow_writer = cash_flow_writer
        self._dividend_reader = dividend_reader
        self._dividend_writer = dividend_writer
        self._corporate_actions_reader = corporate_actions_reader
        self._corporate_actions_writer = corporate_actions_writer
        self._forecast_reader = forecast_reader
        self._forecast_writer = forecast_writer
        self._express_reader = express_reader
        self._express_writer = express_writer

        logger.debug(
            "FundamentalService initialized with CQRS Readers and Writers",
            event="fundamental_service_init_complete",
        )

    # get_* - Single record queries (PIT)

    def get_balance_sheet(
        self, instrument_id: str, as_of_date: date
    ) -> pl.DataFrame | None:
        """Get balance sheet for instrument on date (PIT query)."""
        df = self._balance_sheet_reader.get(instrument_id, as_of_date)
        return None if df.is_empty() else df

    def get_income_statement(
        self, instrument_id: str, as_of_date: date
    ) -> pl.DataFrame | None:
        """Get income statement for instrument on date (PIT query)."""
        df = self._income_statement_reader.get(instrument_id, as_of_date)
        return None if df.is_empty() else df

    def get_cash_flow(
        self, instrument_id: str, as_of_date: date
    ) -> pl.DataFrame | None:
        """Get cash flow for instrument on date (PIT query)."""
        df = self._cash_flow_reader.get(instrument_id, as_of_date)
        return None if df.is_empty() else df

    def get_dividend(self, instrument_id: str, as_of_date: date) -> pl.DataFrame | None:
        """Get dividend data for instrument on date (PIT query)."""
        df = self._dividend_reader.get(instrument_id, as_of_date)
        return None if df.is_empty() else df

    def get_forecast(self, instrument_id: str, as_of_date: date) -> pl.DataFrame | None:
        """Get forecast data for instrument on date (PIT query)."""
        df = self._forecast_reader.get(instrument_id, as_of_date)
        return None if df.is_empty() else df

    def get_express(self, instrument_id: str, as_of_date: date) -> pl.DataFrame | None:
        """Get express report for instrument on date (PIT query)."""
        df = self._express_reader.get(instrument_id, as_of_date)
        return None if df.is_empty() else df

    # list_* - Multi record queries

    def list_corporate_actions(
        self, instrument_id: str, start_date: date, end_date: date
    ) -> pl.DataFrame:
        """List corporate actions for instrument in date range."""
        return self._corporate_actions_reader.get(instrument_id, start_date, end_date)

    # save_* - Write methods

    def save_balance_sheet(self, df: pl.DataFrame) -> int:
        """Save balance sheet data."""
        return self._balance_sheet_writer.write(df)

    def save_income_statement(self, df: pl.DataFrame) -> int:
        """Save income statement data."""
        return self._income_statement_writer.write(df)

    def save_cash_flow(self, df: pl.DataFrame) -> int:
        """Save cash flow data."""
        return self._cash_flow_writer.write(df)

    def save_dividend(self, df: pl.DataFrame) -> int:
        """Save dividend data."""
        return self._dividend_writer.write(df)

    def save_corporate_actions(self, df: pl.DataFrame) -> int:
        """Save corporate actions data."""
        return self._corporate_actions_writer.write(df)

    def save_forecast(self, df: pl.DataFrame) -> int:
        """Save forecast data."""
        return self._forecast_writer.write(df)

    def save_express(self, df: pl.DataFrame) -> int:
        """Save express report data."""
        return self._express_writer.write(df)
