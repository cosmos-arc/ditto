"""
ETF adjustment factor reader.

Provides read-only access to ETF adjustment factors for dividend/split/bonus events
stored in Parquet files with year partitioning. Following design document at
docs/plans/2026-02-09-data-cqrs-refactor.md.
"""

from __future__ import annotations

from pathlib import Path

import polars as pl

from ditto_data.storage.base import ParquetStore, YearlyPartition


class EtfAdjFactorReader:
    """
    ETF adjustment factor data reader.

    Provides read-only access to ETF adjustment factors with year partitioning.
    Uses composition pattern with ParquetStore for all data operations.

    Storage structure:
        data_root/
            market/etf/adj/
                2020.parquet
                2021.parquet
                ...

    Attributes:
        DATASET: Dataset name for ETF adjustment factors.

    """

    DATASET: str = "market/etf/adj"

    def __init__(self, data_root: Path) -> None:
        """
        Initialize EtfAdjFactorReader.

        Args:
            data_root: Root directory for data storage.

        """
        self._store = ParquetStore(data_root, YearlyPartition())

    # ============ Read operations ============

    def read(
        self,
        instrument_ids: list[int] | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        """
        Read adjustment factors from the store.

        Args:
            instrument_ids: Filter by instrument IDs.
            start_date: Start date (YYYY-MM-DD).
            end_date: End date (YYYY-MM-DD).

        Returns:
            DataFrame with matching records.

        """
        return self._store.read(
            self.DATASET,
            instrument_ids=instrument_ids,
            start_date=start_date,
            end_date=end_date,
        )

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
            self.DATASET,
            instrument_ids=instrument_ids,
            start_date=start_date,
            end_date=end_date,
        )

    # ============ Metadata operations ============

    def get_years(self) -> list[int]:
        """
        Get available years for this dataset.

        Returns:
            Sorted list of available years.

        """
        return self._store.get_years(self.DATASET)

    def get_checksum(self, partition_key: str) -> str:
        """
        Get MD5 checksum of a partition.

        Args:
            partition_key: Partition key (e.g., "2024").

        Returns:
            Checksum hex string, or empty string if file doesn't exist.

        """
        return self._store.get_checksum(self.DATASET, partition_key)

    def get_date_range(self) -> tuple[str | None, str | None]:
        """
        Get overall date range for the dataset.

        Returns:
            Tuple of (start_date, end_date) as strings, or (None, None) if empty.

        """
        return self._store.get_date_range(self.DATASET)

    def list_instrument_ids(self) -> list[int]:
        """
        List unique instrument IDs in the dataset.

        Returns:
            Sorted list of unique instrument IDs.

        """
        return self._store.list_instrument_ids(self.DATASET)

    @property
    def data_root(self) -> Path:
        """
        Get the data root directory.

        Returns:
            Data root directory path.

        """
        return self._store.data_root
