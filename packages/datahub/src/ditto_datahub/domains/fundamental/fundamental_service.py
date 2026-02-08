"""Fundamental domain service with unified query/write contract."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Literal

import polars as pl
from ditto_foundation import logger

from ditto_datahub.domains.fundamental.fundamental_store import FundamentalStore

FundamentalDataset = Literal[
    "balance_sheet",
    "income_statement",
    "cash_flow",
    "dividend",
    "corporate_actions",
    "forecast",
    "express",
]


@dataclass(frozen=True)
class FundamentalQuery:
    """Unified query contract for Fundamental domain."""

    dataset: FundamentalDataset
    instrument_id: str
    as_of_date: date | None = None
    start_date: date | None = None
    end_date: date | None = None


@dataclass(frozen=True)
class FundamentalWriteResult:
    """Write result for Fundamental domain service."""

    dataset: FundamentalDataset
    records_written: int


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

    @staticmethod
    def _require_as_of_date(query: FundamentalQuery) -> date:
        if query.as_of_date is None:
            msg = f"{query.dataset} 查询必须提供 as_of_date"
            raise ValueError(msg)
        return query.as_of_date

    def write(
        self,
        dataset: FundamentalDataset,
        df: pl.DataFrame,
    ) -> FundamentalWriteResult:
        """Write dataset via unified contract."""
        writers = {
            "balance_sheet": self._store.write_balance_sheet,
            "income_statement": self._store.write_income_statement,
            "cash_flow": self._store.write_cash_flow,
            "dividend": self._store.write_dividend,
            "corporate_actions": self._store.write_corporate_actions,
            "forecast": self._store.write_forecast,
            "express": self._store.write_express,
        }
        records_written = writers[dataset](df)
        return FundamentalWriteResult(dataset=dataset, records_written=records_written)

    def query(self, query: FundamentalQuery) -> pl.DataFrame:
        """Query dataset via unified contract."""
        if query.dataset == "corporate_actions":
            return self._store.get_corporate_actions(
                query.instrument_id,
                query.start_date,
                query.end_date,
            )

        readers = {
            "balance_sheet": self._store.get_balance_sheet,
            "income_statement": self._store.get_income_statement,
            "cash_flow": self._store.get_cash_flow,
            "dividend": self._store.get_dividend,
            "forecast": self._store.get_forecast,
            "express": self._store.get_express,
        }
        as_of_date = self._require_as_of_date(query)
        return readers[query.dataset](query.instrument_id, as_of_date)
