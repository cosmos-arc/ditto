"""
Base class for Market domain Bars stores.

Provides common functionality for all market bars stores (Stock/ETF/Index),
eliminating code duplication across these domain-specific stores.
"""

from __future__ import annotations

import time
from abc import abstractmethod
from datetime import datetime
from pathlib import Path

import polars as pl
from ditto_foundation import M, logger, traced

from ditto_datahub.models import OnDuplicate
from ditto_datahub.models.storage import WriteResultStore as WriteResult
from ditto_datahub.stores.parquet_store_base import ParquetStoreBase


class MarketBarsStoreBase(ParquetStoreBase):
    """
    Base class for market domain Bars stores.

    This class provides a common implementation for all market bars stores
    (Stock/ETF/Index), eliminating ~500 lines of duplicated code.

    Subclasses only need to:
    1. Define _dataset attribute with their specific dataset name
    2. Implement _get_key_columns() method

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

            def _get_key_columns(self) -> list[str]:
                return ["sid", "trade_date"]

    """

    def __init__(self, data_root: Path) -> None:
        """
        Initialize MarketBarsStoreBase.

        Args:
            data_root: Root directory for data storage.

        """
        super().__init__(data_root)
        # Subclass must set self._dataset in their __init__
        self._dataset: str

    # ============ Abstract methods (must be implemented by subclasses) ============

    @abstractmethod
    def _get_dataset_name(self) -> str:
        """
        Get dataset name for this store.

        Returns:
            Dataset name (e.g., "market/stock/bars").

        """
        ...

    # ============ Read operations ============

    @traced("data.read")
    def read(  # type: ignore[override]
        self,
        sids: list[int] | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        """
        Read market bars data.

        Args:
            sids: Filter by security IDs.
            start_date: Start date (YYYY-MM-DD).
            end_date: End date (YYYY-MM-DD).

        Returns:
            DataFrame with matching records.

        """
        start_time = time.time()
        dataset = self._dataset

        # Determine year range from date filters
        start_year = int(start_date[:4]) if start_date else 1990
        end_year = int(end_date[:4]) if end_date else 2099

        paths = self._collect_paths(dataset, start_year, end_year)

        if not paths:
            logger.info(
                "No data found for query",
                event="data_read_complete",
                dataset=dataset,
                start_date=start_date,
                end_date=end_date,
                row_count=0,
                duration_ms=0,
            )
            return pl.DataFrame()

        # Scan and filter
        lf = pl.scan_parquet([str(p) for p in paths])

        if sids:
            lf = lf.filter(pl.col("sid").is_in(sids))

        if start_date:
            # Convert string to literal date
            start_dt = datetime.strptime(start_date, "%Y-%m-%d").date()
            lf = lf.filter(pl.col("trade_date") >= pl.lit(start_dt))

        if end_date:
            end_dt = datetime.strptime(end_date, "%Y-%m-%d").date()
            lf = lf.filter(pl.col("trade_date") <= pl.lit(end_dt))

        # Ensure sorting for correct unique(keep="last") and result order
        result = (
            lf.sort(["sid", "trade_date"])
            .unique(subset=["sid", "trade_date"], keep="last")
            .sort(["sid", "trade_date"])  # Ensure result is sorted
            .collect()
        )

        duration_ms = (time.time() - start_time) * 1000

        logger.info(
            "Data read completed",
            event="data_read_complete",
            dataset=dataset,
            start_date=start_date,
            end_date=end_date,
            sids_count=len(sids) if sids else None,
            row_count=len(result),
            duration_ms=round(duration_ms, 2),
        )

        # Record metrics
        M.data_records.add(len(result), {"dataset": dataset, "status": "success"})
        M.data_update_duration.record(duration_ms / 1000, {"dataset": dataset})

        return result

    @traced("data.write")
    def write(  # type: ignore[override]
        self,
        df: pl.DataFrame,
        year: int,
        on_duplicate: OnDuplicate = OnDuplicate.ERROR,
    ) -> WriteResult:
        """
        Write market bars data.

        Args:
            df: Data to write.
            year: Year partition.
            on_duplicate: Strategy for handling duplicate data.

        Returns:
            Write result with file path, checksum, and statistics.

        """
        return super().write(self._dataset, df, year, on_duplicate)

    # ============ Metadata operations ============

    def get_years(self) -> list[int]:  # type: ignore[override]
        """
        Get available years for market bars data.

        Returns:
            Sorted list of available years.

        """
        return super().get_years(self._dataset)

    def delete(self, year: int) -> bool:  # type: ignore[override]
        """
        Delete a year partition.

        Args:
            year: Year partition to delete.

        Returns:
            True if deleted, False if file didn't exist.

        """
        return super().delete(self._dataset, year)

    def get_checksum(self, year: int) -> str:  # type: ignore[override]
        """
        Get MD5 checksum of a year partition.

        Args:
            year: Year partition.

        Returns:
            Checksum hex string, or empty string if file doesn't exist.

        """
        return super().get_checksum(self._dataset, year)

    def count(  # type: ignore[override]
        self,
        sids: list[int] | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> int:
        """
        Count records matching filters.

        Args:
            sids: Filter by security IDs.
            start_date: Start date (YYYY-MM-DD).
            end_date: End date (YYYY-MM-DD).

        Returns:
            Number of matching records.

        """
        df = self.read(sids=sids, start_date=start_date, end_date=end_date)
        return len(df)

    def get_date_range(self) -> tuple[str | None, str | None]:  # type: ignore[override]
        """
        Get overall date range for market bars data.

        Returns:
            Tuple of (start_date, end_date) as strings, or (None, None) if empty.

        """
        years = self.get_years()
        if not years:
            return None, None

        # Scan all partitions and find min/max dates
        paths = self._collect_paths(self._dataset, min(years), max(years))
        if not paths:
            return None, None

        lf = pl.scan_parquet([str(p) for p in paths])
        min_max = lf.select(
            [
                pl.col("trade_date").min().alias("min"),
                pl.col("trade_date").max().alias("max"),
            ]
        ).collect()

        if len(min_max) == 0 or min_max["min"][0] is None:
            return None, None

        return str(min_max["min"][0]), str(min_max["max"][0])

    def list_sids(self) -> list[int]:  # type: ignore[override]
        """
        List unique security IDs in market bars data.

        Returns:
            Sorted list of unique security IDs.

        """
        years = self.get_years()
        if not years:
            return []

        paths = self._collect_paths(self._dataset, min(years), max(years))
        if not paths:
            return []

        lf = pl.scan_parquet([str(p) for p in paths])
        result = lf.select(pl.col("sid").unique()).collect()

        sids: list[int] = result["sid"].to_list()
        return sids
