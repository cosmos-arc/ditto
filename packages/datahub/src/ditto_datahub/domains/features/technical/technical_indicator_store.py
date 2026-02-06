"""
TechnicalIndicatorStore for technical indicator data storage.

技术指标数据存储，使用 Parquet 格式按年份分区存储.
"""

from __future__ import annotations

from pathlib import Path

import polars as pl
from ditto_foundation import logger, traced

from ditto_datahub.models import OnDuplicate
from ditto_datahub.models.storage import WriteResultStore as WriteResult
from ditto_datahub.stores.base import ParquetStore, YearlyPartition


class _TechnicalIndicatorParquetStore(ParquetStore):
    """
    Custom ParquetStore for technical indicator data.

    Overrides hook methods to handle indicator-specific logic.
    """

    def _get_key_columns(self) -> list[str]:
        """Return key column names for deduplication."""
        return ["sid", "trade_date", "indicator_id"]

    def _get_sort_columns(self) -> list[str]:
        """Return sort columns."""
        return ["sid", "trade_date", "indicator_id"]


class TechnicalIndicatorStore:
    """
    Technical indicator data storage with year partitioning.

    Stores technical indicator values in Parquet files organized by year.
    Follows the narrow table pattern for flexibility.

    Storage structure:
        data_root/features/technical/indicators_narrow/
            2020.parquet
            2021.parquet
            ...

    Schema:
        sid: Security ID
        trade_date: Trading date
        indicator_id: Indicator identifier (e.g., 'indicator_rsi_14')
        indicator_type: Type category (trend/momentum/volatility/volume)
        value: Indicator value
        calc_time: Calculation timestamp
    """

    def __init__(self, data_root: Path) -> None:
        """
        Initialize TechnicalIndicatorStore.

        Args:
            data_root: Root directory for data storage.

        """
        self._store = _TechnicalIndicatorParquetStore(data_root, YearlyPartition())
        self._dataset = "features/technical/indicators_narrow"

    # ============ Public interface ============

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
                - sid (int)
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
        required = ["sid", "trade_date", "indicator_id", "indicator_type", "value"]
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

    @traced("data.indicator_query")
    def read(
        self,
        sids: list[int] | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        indicator_types: list[str] | None = None,
        indicator_ids: list[str] | None = None,
    ) -> pl.DataFrame:
        """
        Query technical indicator data.

        Args:
            sids: Filter by security IDs (None = all).
            start_date: Start date (YYYY-MM-DD).
            end_date: End date (YYYY-MM-DD).
            indicator_types: Filter by indicator types (None = all).
            indicator_ids: Filter by indicator IDs (None = all).

        Returns:
            DataFrame with indicator data.

        """
        logger.debug(
            "Querying technical indicator data",
            sids=sids,
            start_date=start_date,
            end_date=end_date,
            indicator_types=indicator_types,
            indicator_ids=indicator_ids,
        )

        # Use ParquetStore to get raw data
        df = self._store.read(
            self._dataset, sids=sids, start_date=start_date, end_date=end_date
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

    def delete_partition(self, partition_key: str) -> bool:
        """
        Delete a partition by key.

        Args:
            partition_key: Partition key (e.g., "2024").

        Returns:
            True if deleted, False if file didn't exist.

        """
        return self._store.delete_partition(self._dataset, partition_key)

    def count(
        self,
        sids: list[int] | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> int:
        """
        Count records in the dataset.

        Args:
            sids: Filter by security IDs.
            start_date: Start date (YYYY-MM-DD).
            end_date: End date (YYYY-MM-DD).

        Returns:
            Number of matching records.

        """
        return self._store.count(
            self._dataset, sids=sids, start_date=start_date, end_date=end_date
        )

    def get_date_range(self) -> tuple[str | None, str | None]:
        """
        Get overall date range for the dataset.

        Returns:
            Tuple of (start_date, end_date) as strings, or (None, None) if empty.

        """
        return self._store.get_date_range(self._dataset)

    def list_sids(self) -> list[int]:
        """
        List unique security IDs in the dataset.

        Returns:
            Sorted list of unique security IDs.

        """
        return self._store.list_sids(self._dataset)

    @property
    def data_root(self) -> Path:
        """Get the data root directory."""
        return self._store.data_root
