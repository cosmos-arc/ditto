"""Fundamental domain service with dedicated get/save methods."""

from __future__ import annotations

from datetime import date

import polars as pl
from ditto_platform.foundation import logger

from ditto_data.services.deps import FundamentalReaders, FundamentalWriters


class FundamentalService:
    """
    Fundamental domain unified service.

    Thin wrapper with dependency injection using CQRS pattern.
    Delegates read operations to Readers and write operations to Writers.
    """

    def __init__(
        self,
        read_ports: FundamentalReaders,
        write_ports: FundamentalWriters,
    ) -> None:
        """
        Initialize FundamentalService with CQRS Readers/Writers.

        Args:
            read_ports: Fundamental 域读取依赖（包含所有 Reader）.
            write_ports: Fundamental 域写入依赖（包含所有 Writer）.

        """
        self._read_ports = read_ports
        self._write_ports = write_ports

        logger.debug(
            "FundamentalService initialized with CQRS Readers/Writers",
            event="fundamental_service_init_complete",
        )

    # get_* - Single record queries (PIT)

    def get_balance_sheet(
        self, instrument_id: int, as_of_date: date
    ) -> pl.DataFrame | None:
        """Get balance sheet for instrument on date (PIT query)."""
        df = self._read_ports.balance_sheet.get(instrument_id, as_of_date)
        return None if df.is_empty() else df

    def get_income_statement(
        self, instrument_id: int, as_of_date: date
    ) -> pl.DataFrame | None:
        """Get income statement for instrument on date (PIT query)."""
        df = self._read_ports.income_statement.get(instrument_id, as_of_date)
        return None if df.is_empty() else df

    def get_cash_flow(
        self, instrument_id: int, as_of_date: date
    ) -> pl.DataFrame | None:
        """Get cash flow for instrument on date (PIT query)."""
        df = self._read_ports.cash_flow.get(instrument_id, as_of_date)
        return None if df.is_empty() else df

    def get_dividend(self, instrument_id: int, as_of_date: date) -> pl.DataFrame | None:
        """Get dividend data for instrument on date (PIT query)."""
        df = self._read_ports.dividend.get(instrument_id, as_of_date)
        return None if df.is_empty() else df

    def get_forecast(self, instrument_id: int, as_of_date: date) -> pl.DataFrame | None:
        """Get forecast data for instrument on date (PIT query)."""
        df = self._read_ports.forecast.get(instrument_id, as_of_date)
        return None if df.is_empty() else df

    def get_express(self, instrument_id: int, as_of_date: date) -> pl.DataFrame | None:
        """Get express report for instrument on date (PIT query)."""
        df = self._read_ports.express.get(instrument_id, as_of_date)
        return None if df.is_empty() else df

    # list_* - Multi record queries

    def list_corporate_actions(
        self,
        instrument_id: int,
        start_date: date,
        end_date: date,
        as_of_date: date | None = None,
    ) -> pl.DataFrame:
        """List corporate actions for instrument in date range (with optional PIT)."""
        return self._read_ports.corporate_actions.query(
            instrument_id, start_date, end_date, as_of_date
        )

    # save_* - Write methods

    def save_balance_sheet(self, df: pl.DataFrame) -> int:
        """Save balance sheet data."""
        return self._write_ports.balance_sheet.write(df)

    def save_income_statement(self, df: pl.DataFrame) -> int:
        """Save income statement data."""
        return self._write_ports.income_statement.write(df)

    def save_cash_flow(self, df: pl.DataFrame) -> int:
        """Save cash flow data."""
        return self._write_ports.cash_flow.write(df)

    def save_dividend(self, df: pl.DataFrame) -> int:
        """Save dividend data."""
        return self._write_ports.dividend.write(df)

    def save_corporate_actions(self, df: pl.DataFrame) -> int:
        """Save corporate actions data."""
        return self._write_ports.corporate_actions.write(df)

    def save_forecast(self, df: pl.DataFrame) -> int:
        """Save forecast data."""
        return self._write_ports.forecast.write(df)

    def save_express(self, df: pl.DataFrame) -> int:
        """Save express report data."""
        return self._write_ports.express.write(df)
