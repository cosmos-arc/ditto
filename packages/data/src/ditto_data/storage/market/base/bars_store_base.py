"""
Base class for Market domain Bars stores.

Provides common functionality for all market bars stores (Stock/ETF/Index),
eliminating code duplication across these domain-specific stores.

This base class uses composition pattern with ParquetStore instead of inheritance.
"""

from __future__ import annotations

from abc import abstractmethod
from pathlib import Path

import polars as pl

from ditto_data.models import OnDuplicate
from ditto_data.models.storage import WriteStoreResult
from ditto_data.storage.base import ParquetStore, YearlyPartition


class MarketBarsStoreBase:
    """
    Base class for market domain Bars stores.

    This class provides a common implementation for all market bars stores
    (Stock/ETF/Index) using composition with ParquetStore.

    Subclasses only need to:
    1. Implement _get_dataset() to return their dataset name

    Storage structure:
        data_root/
            market/{asset_class}/bars/
                2020.parquet
                2021.parquet
                ...

    Example:
        class StockBarsStore(MarketBarsStoreBase):
            def __init__(self, data_root: Path) -> None:
                super().__init__(data_root)
                self._dataset = "market/stock/bars"

            def _get_dataset(self) -> str:
                return "market/stock/bars"

    """

    def __init__(self, data_root: Path) -> None:
        """
        Initialize MarketBarsStoreBase.

        Args:
            data_root: Root directory for data storage.

        """
        self._store = ParquetStore(data_root, YearlyPartition())
        # Subclass must set self._dataset in their __init__
        self._dataset: str

    # ============ Abstract methods (must be implemented by subclasses) ============

    @abstractmethod
    def _get_dataset(self) -> str:
        """
        Get dataset name for this store.

        Returns:
            Dataset name (e.g., "market/stock/bars").

        """
        ...

    # ============ Public interface (delegates to ParquetStore) ============

    def read(
        self,
        instrument_ids: list[int] | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        """
        Read bars data from the store.

        Args:
            instrument_ids: Filter by instrument IDs.
            start_date: Start date (YYYY-MM-DD).
            end_date: End date (YYYY-MM-DD).

        Returns:
            DataFrame with matching records.

        """
        return self._store.read(
            self._dataset,
            instrument_ids=instrument_ids,
            start_date=start_date,
            end_date=end_date,
        )

    def write(
        self,
        df: pl.DataFrame,
        year: int,
        on_duplicate: OnDuplicate = OnDuplicate.ERROR,
    ) -> WriteStoreResult:
        """
        Write bars data to the store.

        Args:
            df: DataFrame to write.
            year: Year partition.
            on_duplicate: Duplicate data handling strategy.

        Returns:
            Write result statistics.

        """
        return self._store.write(self._dataset, df, on_duplicate.value, year=year)

    def delete(
        self,
        instrument_ids: list[int] | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> int:
        """
        Delete bars data from the store.

        Args:
            instrument_ids: Filter by instrument IDs.
            start_date: Start date (YYYY-MM-DD).
            end_date: End date (YYYY-MM-DD).

        Returns:
            Number of deleted records.

        """
        return self._store.delete(
            self._dataset,
            instrument_ids=instrument_ids,
            start_date=start_date,
            end_date=end_date,
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

    @property
    def data_root(self) -> Path:
        """Get the data root directory."""
        return self._store.data_root
