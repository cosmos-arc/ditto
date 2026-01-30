"""FundamentalService - Fundamental domain unified service (thin wrapper)."""

from __future__ import annotations

from datetime import date

import polars as pl
from ditto_foundation import logger

from ditto_datahub.domains.fundamental.fundamental_store import FundamentalStore


class FundamentalService:
    """
    Fundamental domain unified service.

    Thin wrapper around FundamentalStore with dependency injection.
    Delegates all operations to the underlying store.
    """

    def __init__(self, fundamental_store: FundamentalStore) -> None:
        """
        Initialize FundamentalService.

        Args:
            fundamental_store: Fundamental domain data storage.

        """
        self._store = fundamental_store

        logger.debug(
            "FundamentalService initialized",
            event="fundamental_service_init_complete",
        )

    # ============ Write methods (delegation) ============

    def write_balance_sheet(self, df: pl.DataFrame) -> int:
        """Write balance sheet data."""
        return self._store.write_balance_sheet(df)

    def write_income_statement(self, df: pl.DataFrame) -> int:
        """Write income statement data."""
        return self._store.write_income_statement(df)

    def write_cash_flow(self, df: pl.DataFrame) -> int:
        """Write cash flow data."""
        return self._store.write_cash_flow(df)

    def write_dividend(self, df: pl.DataFrame) -> int:
        """Write dividend data."""
        return self._store.write_dividend(df)

    def write_corporate_actions(self, df: pl.DataFrame) -> int:
        """Write corporate actions data."""
        return self._store.write_corporate_actions(df)

    def write_forecast(self, df: pl.DataFrame) -> int:
        """Write forecast data."""
        return self._store.write_forecast(df)

    def write_express(self, df: pl.DataFrame) -> int:
        """Write express data."""
        return self._store.write_express(df)

    # ============ Query methods (delegation) ============

    def get_balance_sheet(
        self,
        instrument_id: str,
        as_of_date: date,
    ) -> pl.DataFrame:
        """Query balance sheet data (PIT)."""
        return self._store.get_balance_sheet(instrument_id, as_of_date)

    def get_income_statement(
        self,
        instrument_id: str,
        as_of_date: date,
    ) -> pl.DataFrame:
        """Query income statement data (PIT)."""
        return self._store.get_income_statement(instrument_id, as_of_date)

    def get_cash_flow(
        self,
        instrument_id: str,
        as_of_date: date,
    ) -> pl.DataFrame:
        """Query cash flow data (PIT)."""
        return self._store.get_cash_flow(instrument_id, as_of_date)

    def get_dividend(
        self,
        instrument_id: str,
        as_of_date: date,
    ) -> pl.DataFrame:
        """Query dividend data (PIT)."""
        return self._store.get_dividend(instrument_id, as_of_date)

    def get_corporate_actions(
        self,
        instrument_id: str,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> pl.DataFrame:
        """Query corporate actions data (non-PIT)."""
        return self._store.get_corporate_actions(instrument_id, start_date, end_date)

    def get_forecast(
        self,
        instrument_id: str,
        as_of_date: date,
    ) -> pl.DataFrame:
        """Query forecast data (PIT)."""
        return self._store.get_forecast(instrument_id, as_of_date)

    def get_express(
        self,
        instrument_id: str,
        as_of_date: date,
    ) -> pl.DataFrame:
        """Query express data (PIT)."""
        return self._store.get_express(instrument_id, as_of_date)
