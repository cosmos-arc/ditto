"""
ETF net asset value writer.

Provides write access to ETF net asset value data stored in Parquet files
with year partitioning. Following design document at
docs/plans/2026-02-09-datahub-cqrs-refactor.md.
"""

from __future__ import annotations

from pathlib import Path

import polars as pl

from ditto_datahub.models import OnDuplicate
from ditto_datahub.models.storage import WriteStoreResult as WriteResult
from ditto_datahub.stores.base import ParquetStore, YearlyPartition


class EtfNavWriter:
    """
    ETF net asset value data writer.

    Provides write access to ETF net asset value data with year partitioning.
    Uses composition pattern with ParquetStore for all data operations.

    Storage structure:
        data_root/
            market/etf/nav/
                2020.parquet
                2021.parquet
                ...

    Attributes:
        DATASET: Dataset name for ETF NAV.

    """

    DATASET: str = "market/etf/nav"

    def __init__(self, data_root: Path) -> None:
        """
        Initialize EtfNavWriter.

        Args:
            data_root: Root directory for data storage.

        """
        self._store = ParquetStore(data_root, YearlyPartition())

    # ============ Write operations ============

    def write(
        self,
        df: pl.DataFrame,
        year: int,
        on_duplicate: OnDuplicate = OnDuplicate.ERROR,
    ) -> WriteResult:
        """
        Write NAV data to the store.

        Args:
            df: DataFrame to write.
            year: Year partition.
            on_duplicate: Duplicate data handling strategy.

        Returns:
            Write result statistics.

        """
        return self._store.write(
            self.DATASET,
            df,
            on_duplicate.value,
            year=year,
        )

    def delete(
        self,
        instrument_ids: list[int] | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> int:
        """
        Delete NAV data from the store.

        Args:
            instrument_ids: Filter by instrument IDs.
            start_date: Start date (YYYY-MM-DD).
            end_date: End date (YYYY-MM-DD).

        Returns:
            Number of deleted records.

        """
        return self._store.delete(
            self.DATASET,
            instrument_ids=instrument_ids,
            start_date=start_date,
            end_date=end_date,
        )

    def delete_partition(self, partition_key: str) -> bool:
        """
        Delete a partition by key.

        Args:
            partition_key: Partition key (e.g., "2024").

        Returns:
            True if deleted, False if file didn't exist.

        """
        return self._store.delete_partition(self.DATASET, partition_key)

    # ============ Metadata operations ============

    def get_checksum(self, partition_key: str) -> str:
        """
        Get MD5 checksum of a partition.

        Args:
            partition_key: Partition key (e.g., "2024").

        Returns:
            Checksum hex string, or empty string if file doesn't exist.

        """
        return self._store.get_checksum(self.DATASET, partition_key)

    @property
    def data_root(self) -> Path:
        """
        Get the data root directory.

        Returns:
            Data root directory path.

        """
        return self._store.data_root
