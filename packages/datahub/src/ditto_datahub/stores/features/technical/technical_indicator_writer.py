"""
TechnicalIndicator writer for CQRS pattern.

Provides write access to technical indicator data.
Following design document at docs/plans/2026-02-09-datahub-cqrs-refactor.md
"""

from __future__ import annotations

from pathlib import Path

import polars as pl
from ditto_foundation import logger, traced

from ditto_datahub.models import OnDuplicate
from ditto_datahub.models.storage import WriteStoreResult as WriteResult
from ditto_datahub.stores.base import ParquetStore, YearlyPartition


class _TechnicalIndicatorParquetWriter(ParquetStore):
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


class TechnicalIndicatorWriter:
    """
    Technical indicator data writer with year partitioning.

    Provides write access to technical indicator values in Parquet files
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
        Initialize TechnicalIndicatorWriter.

        Args:
            data_root: Root directory for data storage.

        """
        self._store = _TechnicalIndicatorParquetWriter(
            Path(data_root),
            YearlyPartition(),
        )
        self._dataset = "features/technical/indicators_narrow"

    @traced("data.indicator_write")
    def write(
        self,
        df: pl.DataFrame,
        year: int,
        on_duplicate: OnDuplicate = OnDuplicate.ERROR,
    ) -> WriteResult:
        """
        Write technical indicator data.

        Args:
            df: DataFrame with columns:
                - instrument_id (int)
                - trade_date (date or str YYYY-MM-DD)
                - indicator_id (str)
                - indicator_type (str)
                - value (float)
                - calc_time (str or datetime)
            year: Year partition for writing.
            on_duplicate: How to handle duplicates.

        Returns:
            Write result with statistics.

        Raises:
            ValueError: If required columns are missing.

        """
        logger.info(
            "Starting technical indicator data write",
            record_count=len(df),
            year=year,
        )

        # Validate required columns
        required = [
            "instrument_id",
            "trade_date",
            "indicator_id",
            "indicator_type",
            "value",
        ]
        missing = [col for col in required if col not in df.columns]
        if missing:
            msg = f"Missing required columns: {missing}"
            raise ValueError(msg)

        # Use ParquetStore write implementation
        result = self._store.write(self._dataset, df, on_duplicate.value, year=year)

        logger.info(
            "Technical indicator data written successfully",
            record_count=len(df),
            year=year,
            added=result.added,
            updated=result.updated,
        )

        return result

    def delete_partition(self, partition_key: str) -> bool:
        """
        Delete a partition by key.

        Args:
            partition_key: Partition key (e.g., "2024").

        Returns:
            True if deleted, False if file didn't exist.

        """
        return self._store.delete_partition(self._dataset, partition_key)

    @property
    def data_root(self) -> Path:
        """Get the data root directory."""
        return self._store.data_root
