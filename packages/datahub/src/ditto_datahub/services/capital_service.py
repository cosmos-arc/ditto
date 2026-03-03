"""Capital domain service with dedicated query/write methods."""

from __future__ import annotations

from datetime import date

import polars as pl
from ditto_infra.foundation import logger

from ditto_datahub.services.ports import CapitalReadPorts, CapitalWritePorts


class CapitalService:
    """
    Capital domain unified service.

    Thin wrapper around Reader/Writer components with dependency injection.
    Delegates all operations to the underlying readers and writers.
    """

    def __init__(
        self,
        read_ports: CapitalReadPorts,
        write_ports: CapitalWritePorts,
    ) -> None:
        """
        Initialize CapitalService.

        Args:
            read_ports: Capital domain read ports (all readers).
            write_ports: Capital domain write ports (all writers).

        """
        self._read_ports = read_ports
        self._write_ports = write_ports

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
        return self._read_ports.margin_trading.get(instrument_id, as_of_date)

    def get_pledge_ratio(self, instrument_id: str, as_of_date: date) -> pl.DataFrame:
        """
        Query pledge ratio data for an instrument.

        Args:
            instrument_id: The instrument ID to query.
            as_of_date: The point-in-time query date.

        Returns:
            DataFrame with pledge ratio data.

        """
        return self._read_ports.pledge_ratio.get(instrument_id, as_of_date)

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
        return self._read_ports.valuation_metrics.get(instrument_id, as_of_date)

    def get_index_composition(self, index_id: str, as_of_date: date) -> pl.DataFrame:
        """
        Query index composition data for an index.

        Args:
            index_id: The index ID to query.
            as_of_date: The point-in-time query date.

        Returns:
            DataFrame with index composition data.

        """
        return self._read_ports.index_composition.get(index_id, as_of_date)

    # Write methods (save_*)

    def save_margin_trading(self, df: pl.DataFrame) -> int:
        """
        Save margin trading data.

        Args:
            df: DataFrame with margin trading data to save.

        Returns:
            Number of records written.

        """
        return self._write_ports.margin_trading.write(df)

    def save_pledge_ratio(self, df: pl.DataFrame) -> int:
        """
        Save pledge ratio data.

        Args:
            df: DataFrame with pledge ratio data to save.

        Returns:
            Number of records written.

        """
        return self._write_ports.pledge_ratio.write(df)

    def save_valuation_metrics(self, df: pl.DataFrame) -> int:
        """
        Save valuation metrics data.

        Args:
            df: DataFrame with valuation metrics data to save.

        Returns:
            Number of records written.

        """
        return self._write_ports.valuation_metrics.write(df)

    def save_index_composition(self, df: pl.DataFrame) -> int:
        """
        Save index composition data.

        Args:
            df: DataFrame with index composition data to save.

        Returns:
            Number of records written.

        """
        return self._write_ports.index_composition.write(df)
