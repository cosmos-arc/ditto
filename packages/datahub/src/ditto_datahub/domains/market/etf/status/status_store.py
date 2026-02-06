"""
ETF status storage with year partitioning.

Stores status information for ETFs in Parquet files with year
partitioning. Following design document at docs/design/02_data_design.md.
"""

from __future__ import annotations

from pathlib import Path

import polars as pl

from ditto_datahub.models.storage import WriteResultStore as WriteResult
from ditto_datahub.stores.base import ParquetStore, YearlyPartition


class EtfStatusStore:
    """
    ETF status data storage with year partitioning.

    Storage structure:
        data_root/
            market/etf/status/
                2020.parquet
                2021.parquet
                ...

    This store is specialized for ETF status and uses a fixed
    dataset name "market/etf/status". All operations are delegated to ParquetStore.

    """

    def __init__(self, data_root: Path) -> None:
        """
        Initialize EtfStatusStore.

        Args:
            data_root: Root directory for data storage.

        """
        self._store = ParquetStore(data_root, YearlyPartition())
        self._dataset = "market/etf/status"

    # ============ Public interface ============

    def read(
        self,
        sids: list[int] | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        """
        Read status data from the store.

        Args:
            sids: Filter by security IDs.
            start_date: Start date (YYYY-MM-DD).
            end_date: End date (YYYY-MM-DD).

        Returns:
            DataFrame with matching records.

        """
        return self._store.read(
            self._dataset, sids=sids, start_date=start_date, end_date=end_date
        )

    def write(
        self,
        df: pl.DataFrame,
        year: int,
        on_duplicate: str = "error",
    ) -> WriteResult:
        """
        Write status data to the store.

        Args:
            df: DataFrame to write.
            year: Year partition.
            on_duplicate: Duplicate data handling strategy.

        Returns:
            Write result statistics.

        """
        return self._store.write(self._dataset, df, on_duplicate, year=year)

    def delete(
        self,
        sids: list[int] | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> int:
        """
        Delete status data from the store.

        Args:
            sids: Filter by security IDs.
            start_date: Start date (YYYY-MM-DD).
            end_date: End date (YYYY-MM-DD).

        Returns:
            Number of deleted records.

        """
        return self._store.delete(
            self._dataset, sids=sids, start_date=start_date, end_date=end_date
        )

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
    def data_root(self):
        """Get the data root directory."""
        return self._store.data_root
