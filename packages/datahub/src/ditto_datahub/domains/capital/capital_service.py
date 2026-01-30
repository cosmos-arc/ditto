"""CapitalService - Capital domain unified service (thin wrapper)."""

from __future__ import annotations

from datetime import date

import polars as pl
from ditto_foundation import logger

from ditto_datahub.domains.capital.capital_store import CapitalStore


class CapitalService:
    """
    Capital domain unified service.

    Thin wrapper around CapitalStore with dependency injection.
    Delegates all operations to the underlying store.
    """

    def __init__(self, capital_store: CapitalStore) -> None:
        """
        Initialize CapitalService.

        Args:
            capital_store: Capital domain data storage.

        """
        self._store = capital_store

        logger.debug(
            "CapitalService initialized",
            event="capital_service_init_complete",
        )

    # ============ Write methods (delegation) ============

    def write_margin_trading(self, df: pl.DataFrame) -> int:
        """Write margin trading data."""
        return self._store.write_margin_trading(df)

    def write_pledge_ratio(self, df: pl.DataFrame) -> int:
        """Write pledge ratio data."""
        return self._store.write_pledge_ratio(df)

    def write_valuation_metrics(self, df: pl.DataFrame) -> int:
        """Write valuation metrics data."""
        return self._store.write_valuation_metrics(df)

    def write_futures(self, df: pl.DataFrame) -> int:
        """Write futures data."""
        return self._store.write_futures(df)

    def write_index_composition(self, df: pl.DataFrame) -> int:
        """Write index composition data."""
        return self._store.write_index_composition(df)

    # ============ Query methods (delegation) ============

    def get_margin_trading(
        self,
        instrument_id: str,
        as_of_date: date,
    ) -> pl.DataFrame:
        """Query margin trading data (PIT)."""
        return self._store.get_margin_trading(instrument_id, as_of_date)

    def get_pledge_ratio(
        self,
        instrument_id: str,
        as_of_date: date,
    ) -> pl.DataFrame:
        """Query pledge ratio data (PIT)."""
        return self._store.get_pledge_ratio(instrument_id, as_of_date)

    def get_valuation_metrics(
        self,
        instrument_id: str,
        as_of_date: date,
    ) -> pl.DataFrame:
        """Query valuation metrics data (PIT)."""
        return self._store.get_valuation_metrics(instrument_id, as_of_date)

    def get_futures(
        self,
        instrument_id: str,
        as_of_date: date,
    ) -> pl.DataFrame:
        """Query futures data (PIT)."""
        return self._store.get_futures(instrument_id, as_of_date)

    def get_index_composition(
        self,
        index_id: str,
        as_of_date: date,
    ) -> pl.DataFrame:
        """Query index composition data (PIT)."""
        return self._store.get_index_composition(index_id, as_of_date)
