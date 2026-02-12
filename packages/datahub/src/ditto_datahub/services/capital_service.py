"""Capital domain service with dedicated query/write methods."""

from __future__ import annotations

from datetime import date

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

    # Query methods (get_*)

    def get_margin_trading(self, instrument_id: str, as_of_date: date) -> pl.DataFrame:
        """
        Query margin trading data for an instrument.

        Args:
            instrument_id: The instrument ID to query.
            as_of_date: The point-in-time query date.

        Returns:
            DataFrame with margin trading data.

        """
        return self._margin_trading_reader.get(instrument_id, as_of_date)

    def get_pledge_ratio(self, instrument_id: str, as_of_date: date) -> pl.DataFrame:
        """
        Query pledge ratio data for an instrument.

        Args:
            instrument_id: The instrument ID to query.
            as_of_date: The point-in-time query date.

        Returns:
            DataFrame with pledge ratio data.

        """
        return self._pledge_ratio_reader.get(instrument_id, as_of_date)

    def get_valuation_metrics(
        self, instrument_id: str, as_of_date: date
    ) -> pl.DataFrame:
        """
        Query valuation metrics data for an instrument.

        Args:
            instrument_id: The instrument ID to query.
            as_of_date: The point-in-time query date.

        Returns:
            DataFrame with valuation metrics data.

        """
        return self._valuation_metrics_reader.get(instrument_id, as_of_date)

    def get_futures(self, instrument_id: str, as_of_date: date) -> pl.DataFrame:
        """
        Query futures data for an instrument.

        Args:
            instrument_id: The instrument ID to query.
            as_of_date: The point-in-time query date.

        Returns:
            DataFrame with futures data.

        """
        return self._futures_reader.get(instrument_id, as_of_date)

    def get_index_composition(self, index_id: str, as_of_date: date) -> pl.DataFrame:
        """
        Query index composition data for an index.

        Args:
            index_id: The index ID to query.
            as_of_date: The point-in-time query date.

        Returns:
            DataFrame with index composition data.

        """
        return self._index_composition_reader.get(index_id, as_of_date)

    # Write methods (save_*)

    def save_margin_trading(self, df: pl.DataFrame) -> int:
        """
        Save margin trading data.

        Args:
            df: DataFrame with margin trading data to save.

        Returns:
            Number of records written.

        """
        return self._margin_trading_writer.write(df)

    def save_pledge_ratio(self, df: pl.DataFrame) -> int:
        """
        Save pledge ratio data.

        Args:
            df: DataFrame with pledge ratio data to save.

        Returns:
            Number of records written.

        """
        return self._pledge_ratio_writer.write(df)

    def save_valuation_metrics(self, df: pl.DataFrame) -> int:
        """
        Save valuation metrics data.

        Args:
            df: DataFrame with valuation metrics data to save.

        Returns:
            Number of records written.

        """
        return self._valuation_metrics_writer.write(df)

    def save_futures(self, df: pl.DataFrame) -> int:
        """
        Save futures data.

        Args:
            df: DataFrame with futures data to save.

        Returns:
            Number of records written.

        """
        return self._futures_writer.write(df)

    def save_index_composition(self, df: pl.DataFrame) -> int:
        """
        Save index composition data.

        Args:
            df: DataFrame with index composition data to save.

        Returns:
            Number of records written.

        """
        return self._index_composition_writer.write(df)
