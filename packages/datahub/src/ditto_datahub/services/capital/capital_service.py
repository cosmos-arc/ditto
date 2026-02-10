"""Capital domain service with unified query/write contract."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Literal

import polars as pl
from ditto_foundation import logger

from ditto_datahub.stores.capital.futures.futures_reader import FuturesReader
from ditto_datahub.stores.capital.futures.futures_writer import FuturesWriter
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

    Thin wrapper around Reader/Writer components with dependency injection.
    Delegates all operations to the underlying readers and writers.
    """

    def __init__(  # noqa: PLR0913
        self,
        margin_trading_reader: MarginTradingReader,
        margin_trading_writer: MarginTradingWriter,
        pledge_ratio_reader: PledgeRatioReader,
        pledge_ratio_writer: PledgeRatioWriter,
        valuation_metrics_reader: ValuationMetricsReader,
        valuation_metrics_writer: ValuationMetricsWriter,
        futures_reader: FuturesReader,
        futures_writer: FuturesWriter,
        index_composition_reader: IndexCompositionReader,
        index_composition_writer: IndexCompositionWriter,
    ) -> None:
        """
        Initialize CapitalService.

        Args:
            margin_trading_reader: Margin trading data reader.
            margin_trading_writer: Margin trading data writer.
            pledge_ratio_reader: Pledge ratio data reader.
            pledge_ratio_writer: Pledge ratio data writer.
            valuation_metrics_reader: Valuation metrics data reader.
            valuation_metrics_writer: Valuation metrics data writer.
            futures_reader: Futures data reader.
            futures_writer: Futures data writer.
            index_composition_reader: Index composition data reader.
            index_composition_writer: Index composition data writer.

        """
        self._margin_trading_reader = margin_trading_reader
        self._margin_trading_writer = margin_trading_writer
        self._pledge_ratio_reader = pledge_ratio_reader
        self._pledge_ratio_writer = pledge_ratio_writer
        self._valuation_metrics_reader = valuation_metrics_reader
        self._valuation_metrics_writer = valuation_metrics_writer
        self._futures_reader = futures_reader
        self._futures_writer = futures_writer
        self._index_composition_reader = index_composition_reader
        self._index_composition_writer = index_composition_writer

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
            "margin_trading": self._margin_trading_writer.write,
            "pledge_ratio": self._pledge_ratio_writer.write,
            "valuation_metrics": self._valuation_metrics_writer.write,
            "futures": self._futures_writer.write,
            "index_composition": self._index_composition_writer.write,
        }
        records_written = writers[dataset](df)
        return CapitalWriteResult(dataset=dataset, records_written=records_written)

    def query(self, query: CapitalQuery) -> pl.DataFrame:
        """Query dataset via unified contract."""
        if query.dataset == "index_composition":
            return self._index_composition_reader.get(
                self._require_index_id(query), query.as_of_date
            )

        readers = {
            "margin_trading": self._margin_trading_reader.get,
            "pledge_ratio": self._pledge_ratio_reader.get,
            "valuation_metrics": self._valuation_metrics_reader.get,
            "futures": self._futures_reader.get,
        }
        instrument_id = self._require_instrument_id(query)
        return readers[query.dataset](instrument_id, query.as_of_date)
