"""Capital domain service with unified query/write contract."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Literal

import polars as pl
from ditto_foundation import logger

from ditto_datahub.stores.capital.capital_store import CapitalStore

CapitalDataset = Literal[
    "margin_trading",
    "pledge_ratio",
    "valuation_metrics",
    "futures",
    "index_composition",
]


@dataclass(frozen=True)
class CapitalQuery:
    """Unified query contract for Capital domain."""

    dataset: CapitalDataset
    as_of_date: date
    instrument_id: str | None = None
    index_id: str | None = None


@dataclass(frozen=True)
class CapitalWriteResult:
    """Write result for Capital domain service."""

    dataset: CapitalDataset
    records_written: int


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

    @staticmethod
    def _require_instrument_id(query: CapitalQuery) -> str:
        if query.instrument_id is None:
            msg = f"{query.dataset} 查询必须提供 instrument_id"
            raise ValueError(msg)
        return query.instrument_id

    @staticmethod
    def _require_index_id(query: CapitalQuery) -> str:
        if query.index_id is None:
            msg = "index_composition 查询必须提供 index_id"
            raise ValueError(msg)
        return query.index_id

    def write(self, dataset: CapitalDataset, df: pl.DataFrame) -> CapitalWriteResult:
        """Write dataset via unified contract."""
        writers = {
            "margin_trading": self._store.write_margin_trading,
            "pledge_ratio": self._store.write_pledge_ratio,
            "valuation_metrics": self._store.write_valuation_metrics,
            "futures": self._store.write_futures,
            "index_composition": self._store.write_index_composition,
        }
        records_written = writers[dataset](df)
        return CapitalWriteResult(dataset=dataset, records_written=records_written)

    def query(self, query: CapitalQuery) -> pl.DataFrame:
        """Query dataset via unified contract."""
        if query.dataset == "index_composition":
            return self._store.get_index_composition(
                self._require_index_id(query), query.as_of_date
            )

        readers = {
            "margin_trading": self._store.get_margin_trading,
            "pledge_ratio": self._store.get_pledge_ratio,
            "valuation_metrics": self._store.get_valuation_metrics,
            "futures": self._store.get_futures,
        }
        instrument_id = self._require_instrument_id(query)
        return readers[query.dataset](instrument_id, query.as_of_date)
