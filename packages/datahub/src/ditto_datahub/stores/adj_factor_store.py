"""
AdjFactorStore for stock adjustment factors.

⚠️ DEPRECATED: 此模块已迁移到 domains/market/stock/adj/

请使用新的导入路径：
    from ditto_datahub.domains.market.stock.adj import StockAdjFactorStore

This module provides backward compatibility by maintaining the old storage path
(adj_factor/) while the new implementation uses market/stock/adj/.
"""

from __future__ import annotations

import time
import warnings
from datetime import datetime
from pathlib import Path

import polars as pl
from ditto_foundation import M, logger, traced

from ditto_datahub.models import OnDuplicate
from ditto_datahub.models.storage import WriteResultStore as WriteResult
from ditto_datahub.stores.parquet_store_base import ParquetStoreBase


class AdjFactorStore(ParquetStoreBase):
    """
    Deprecated backward-compatible wrapper for adjustment factor storage.

    This class maintains the OLD API and OLD storage path (adj_factor/) for
    backward compatibility. New code should use StockAdjFactorStore from
    ditto_datahub.domains.market.stock.adj instead.

    Storage structure (LEGACY):
        data_root/
            adj_factor/
                2020.parquet
                2021.parquet
                ...

    The new StockAdjFactorStore uses:
        data_root/
            market/stock/adj/
                2020.parquet
                2021.parquet
                ...
    """

    def __init__(self, data_root: Path) -> None:
        """Initialize with deprecation warning and legacy dataset name."""
        super().__init__(data_root)
        self._dataset = "adj_factor"  # Legacy path for backward compatibility
        warnings.warn(
            "AdjFactorStore 已迁移到 ditto_datahub.domains.market.stock.adj。",
            DeprecationWarning,
            stacklevel=2,
        )

    # ============ Key columns ============

    def _get_key_columns(self) -> list[str]:
        """Return key column names for deduplication."""
        return ["sid", "trade_date"]

    # ============ Read operations ============

    @traced("data.read")
    def read(
        self,
        dataset: str,
        sids: list[int] | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        """
        Read adjustment factor data (deprecated API).

        Args:
            dataset: Dataset name (ignored, always uses "adj_factor").
            sids: Filter by security IDs.
            start_date: Start date (YYYY-MM-DD).
            end_date: End date (YYYY-MM-DD).

        Returns:
            DataFrame with matching records.

        """
        start_time = time.time()

        # Determine year range from date filters
        start_year = int(start_date[:4]) if start_date else 1990
        end_year = int(end_date[:4]) if end_date else 2099

        paths = self._collect_paths(self._dataset, start_year, end_year)

        if not paths:
            logger.info(
                "No data found for query",
                event="data_read_complete",
                dataset=self._dataset,
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
            start_dt = datetime.strptime(start_date, "%Y-%m-%d").date()
            lf = lf.filter(pl.col("trade_date") >= pl.lit(start_dt))

        if end_date:
            end_dt = datetime.strptime(end_date, "%Y-%m-%d").date()
            lf = lf.filter(pl.col("trade_date") <= pl.lit(end_dt))

        # Ensure sorting for correct unique(keep="last") and result order
        result = (
            lf.sort(["sid", "trade_date"])
            .unique(subset=["sid", "trade_date"], keep="last")
            .sort(["sid", "trade_date"])
            .collect()
        )

        duration_ms = (time.time() - start_time) * 1000

        logger.info(
            "Data read completed",
            event="data_read_complete",
            dataset=self._dataset,
            start_date=start_date,
            end_date=end_date,
            sids_count=len(sids) if sids else None,
            row_count=len(result),
            duration_ms=round(duration_ms, 2),
        )

        # Record metrics
        M.data_records.add(len(result), {"dataset": self._dataset, "status": "success"})
        M.data_update_duration.record(duration_ms / 1000, {"dataset": self._dataset})

        return result

    @traced("data.write")
    def write(
        self,
        dataset: str,
        df: pl.DataFrame,
        year: int,
        on_duplicate: OnDuplicate = OnDuplicate.ERROR,
    ) -> WriteResult:
        """
        Write adjustment factor data (deprecated API).

        Args:
            dataset: Dataset name (ignored, always uses "adj_factor").
            df: Data to write.
            year: Year partition.
            on_duplicate: Strategy for handling duplicate data.

        Returns:
            Write result with file path, checksum, and statistics.

        """
        return super().write(self._dataset, df, year, on_duplicate)

    # ============ Metadata operations ============

    def get_years(self, dataset: str) -> list[int]:
        """
        Get available years (deprecated API).

        Args:
            dataset: Dataset name (ignored).

        Returns:
            Sorted list of available years.

        """
        return super().get_years(self._dataset)

    def delete(self, dataset: str, year: int) -> bool:
        """
        Delete a year partition (deprecated API).

        Args:
            dataset: Dataset name (ignored).
            year: Year partition to delete.

        Returns:
            True if deleted, False if file didn't exist.

        """
        return super().delete(self._dataset, year)

    def get_checksum(self, dataset: str, year: int) -> str:
        """
        Get MD5 checksum of a year partition (deprecated API).

        Args:
            dataset: Dataset name (ignored).
            year: Year partition.

        Returns:
            Checksum hex string, or empty string if file doesn't exist.

        """
        return super().get_checksum(self._dataset, year)

    def count(
        self,
        dataset: str,
        sids: list[int] | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> int:
        """
        Count records (deprecated API).

        Args:
            dataset: Dataset name (ignored).
            sids: Filter by security IDs.
            start_date: Start date (YYYY-MM-DD).
            end_date: End date (YYYY-MM-DD).

        Returns:
            Number of matching records.

        """
        df = self.read(
            self._dataset, sids=sids, start_date=start_date, end_date=end_date
        )
        return len(df)

    def get_date_range(self, dataset: str) -> tuple[str | None, str | None]:
        """
        Get overall date range (deprecated API).

        Args:
            dataset: Dataset name (ignored).

        Returns:
            Tuple of (start_date, end_date) as strings, or (None, None) if empty.

        """
        years = self.get_years(self._dataset)
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

    def list_sids(self, dataset: str) -> list[int]:
        """
        List unique security IDs (deprecated API).

        Args:
            dataset: Dataset name (ignored).

        Returns:
            Sorted list of unique security IDs.

        """
        years = self.get_years(self._dataset)
        if not years:
            return []

        paths = self._collect_paths(self._dataset, min(years), max(years))
        if not paths:
            return []

        lf = pl.scan_parquet([str(p) for p in paths])
        result = lf.select(pl.col("sid").unique()).collect()

        sids: list[int] = result["sid"].to_list()
        return sids


# Import the new store for convenience
# NOTE: Must be after class definition to avoid circular import
from ditto_datahub.domains.market.stock.adj.adj_factor_store import (  # noqa: E402
    StockAdjFactorStore,
)

__all__ = ["AdjFactorStore", "StockAdjFactorStore"]
