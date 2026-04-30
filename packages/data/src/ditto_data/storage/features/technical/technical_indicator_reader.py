"""
TechnicalIndicator reader for CQRS pattern.

Provides read-only access to technical indicator data.
Following design document at docs/plans/2026-02-09-data-cqrs-refactor.md
"""

from __future__ import annotations

from pathlib import Path

import polars as pl
from ditto_platform.foundation import logger, traced

from ditto_data.storage.base import ParquetStore, YearlyPartition


class _TechnicalIndicatorParquetReader(ParquetStore):
    """
    Custom ParquetStore for technical indicator data.

    Overrides hook methods to handle indicator-specific logic.
    """

    def _get_key_columns(self) -> list[str]:
        """Return key column names for deduplication."""
        return ["instrument_id", "trade_date", "indicator_id"]

    def _get_sort_columns(self) -> list[str]:
        """Return sort columns."""
        return ["instrument_id", "trade_date", "indicator_id"]


class TechnicalIndicatorReader:
    """
    Technical indicator data reader with year partitioning.

    Provides read-only access to technical indicator values in Parquet files
    organized by year. Follows the narrow table pattern for flexibility.

    Storage structure:
        data_root/features/technical/indicators_narrow/
            2020.parquet
            2021.parquet
            ...

    Schema:
        instrument_id: Instrument ID
        trade_date: Trading date
        indicator_id: Indicator identifier (e.g., 'indicator_rsi_14')
        indicator_type: Type category (trend/momentum/volatility/volume)
        value: Indicator value
        calc_time: Calculation timestamp

    Attributes:
        _store: Custom ParquetStore for technical indicator data.
        _dataset: Dataset path within data_root.

    """

    def __init__(self, data_root: str | Path) -> None:
        """
        Initialize TechnicalIndicatorReader.

        Args:
            data_root: Root directory for data storage.

        """
        self._store = _TechnicalIndicatorParquetReader(
            Path(data_root),
            YearlyPartition(),
        )
        self._dataset = "features/technical/indicators_narrow"

    @traced("data.indicator_query")
    def read(
        self,
        instrument_ids: list[int] | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        indicator_types: list[str] | None = None,
        indicator_ids: list[str] | None = None,
    ) -> pl.DataFrame:
        """
        Query technical indicator data.

        Args:
            instrument_ids: Filter by instrument IDs (None = all).
            start_date: Start date (YYYY-MM-DD).
            end_date: End date (YYYY-MM-DD).
            indicator_types: Filter by indicator types (None = all).
            indicator_ids: Filter by indicator IDs (None = all).

        Returns:
            DataFrame with indicator data.

        """
        logger.debug(
            "Querying technical indicator data",
            instrument_ids=instrument_ids,
            start_date=start_date,
            end_date=end_date,
            indicator_types=indicator_types,
            indicator_ids=indicator_ids,
        )

        # Use ParquetStore to get raw data
        df = self._store.read(
            self._dataset,
            instrument_ids=instrument_ids,
            start_date=start_date,
            end_date=end_date,
        )

        # Apply indicator_id filter
        if not df.is_empty() and indicator_ids:
            df = df.filter(pl.col("indicator_id").is_in(indicator_ids))

        # Apply indicator_type filter
        if not df.is_empty() and indicator_types:
            df = df.filter(pl.col("indicator_type").is_in(indicator_types))

        return df

    # ============ Metadata operations ============

    def get_years(self) -> list[int]:
        """Get available years for this dataset."""
        return self._store.get_years(self._dataset)

    def get_checksum(self, partition_key: str) -> str:
        """
        Get MD5 checksum of a partition.

        Args:
            partition_key: Partition key (e.g., "2024").

        Returns:
            Checksum hex string, or empty string if file doesn't exist.

        """
        return self._store.get_checksum(self._dataset, partition_key)

    def count(
        self,
        instrument_ids: list[int] | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> int:
        """
        Count records in the dataset.

        Args:
            instrument_ids: Filter by instrument IDs.
            start_date: Start date (YYYY-MM-DD).
            end_date: End date (YYYY-MM-DD).

        Returns:
            Number of matching records.

        """
        return self._store.count(
            self._dataset,
            instrument_ids=instrument_ids,
            start_date=start_date,
            end_date=end_date,
        )

    def get_date_range(self) -> tuple[str | None, str | None]:
        """
        Get overall date range for the dataset.

        Returns:
            Tuple of (start_date, end_date) as strings, or (None, None) if empty.

        """
        return self._store.get_date_range(self._dataset)

    def list_instrument_ids(self) -> list[int]:
        """
        List unique instrument IDs in the dataset.

        Returns:
            Sorted list of unique instrument IDs.

        """
        return self._store.list_instrument_ids(self._dataset)
