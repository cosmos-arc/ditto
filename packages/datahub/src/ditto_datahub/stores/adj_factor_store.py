"""
AdjFactorStore for stock adjustment factors.

⚠️ DEPRECATED: 此模块已迁移到 domains/market/stock/adj/

请使用新的导入路径：
    from ditto_datahub.domains.market.stock.adj import StockAdjFactorStore
"""

from __future__ import annotations

import warnings
from pathlib import Path

import polars as pl

# Import the new store
from ditto_datahub.domains.market.stock.adj.adj_factor_store import (
    StockAdjFactorStore,
)
from ditto_datahub.models import OnDuplicate
from ditto_datahub.models.storage import WriteResultStore as WriteResult


class AdjFactorStore(StockAdjFactorStore):
    """
    Deprecated backward-compatible wrapper for StockAdjFactorStore.

    This class maintains the old API with the dataset parameter for
    backward compatibility. It wraps the new StockAdjFactorStore and
    automatically passes the dataset name.
    """

    def __init__(self, data_root: Path) -> None:
        """Initialize with deprecation warning."""
        super().__init__(data_root)
        warnings.warn(
            "AdjFactorStore 已迁移到 ditto_datahub.domains.market.stock.adj。",
            DeprecationWarning,
            stacklevel=2,
        )

    def read(  # type: ignore[override]
        self,
        dataset: str,
        sids: list[int] | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        """
        Read adjustment factor data (deprecated API).

        Args:
            dataset: Dataset name (ignored, always uses "market/stock/adj").
            sids: Filter by security IDs.
            start_date: Start date (YYYY-MM-DD).
            end_date: End date (YYYY-MM-DD).

        Returns:
            DataFrame with matching records.

        """
        # Ignore the dataset parameter and use the parent's read method
        return super().read(sids=sids, start_date=start_date, end_date=end_date)

    def write(  # type: ignore[override]
        self,
        dataset: str,
        df: pl.DataFrame,
        year: int,
        on_duplicate: OnDuplicate = OnDuplicate.ERROR,
    ) -> WriteResult:
        """
        Write adjustment factor data (deprecated API).

        Args:
            dataset: Dataset name (ignored, always uses "market/stock/adj").
            df: Data to write.
            year: Year partition.
            on_duplicate: Strategy for handling duplicate data.

        Returns:
            Write result with file path, checksum, and statistics.

        """
        # Ignore the dataset parameter and use the parent's write method
        return super().write(df, year, on_duplicate)

    def get_years(self, dataset: str) -> list[int]:  # type: ignore[override]
        """
        Get available years (deprecated API).

        Args:
            dataset: Dataset name (ignored).

        Returns:
            Sorted list of available years.

        """
        return super().get_years()

    def delete(self, dataset: str, year: int) -> bool:  # type: ignore[override]
        """
        Delete a year partition (deprecated API).

        Args:
            dataset: Dataset name (ignored).
            year: Year partition to delete.

        Returns:
            True if deleted, False if file didn't exist.

        """
        return super().delete(year)

    def get_checksum(self, dataset: str, year: int) -> str:  # type: ignore[override]
        """
        Get MD5 checksum of a year partition (deprecated API).

        Args:
            dataset: Dataset name (ignored).
            year: Year partition.

        Returns:
            Checksum hex string, or empty string if file doesn't exist.

        """
        return super().get_checksum(year)

    def count(  # type: ignore[override]
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
        return super().count(sids, start_date, end_date)

    def get_date_range(self, dataset: str) -> tuple[str | None, str | None]:  # type: ignore[override]
        """
        Get overall date range (deprecated API).

        Args:
            dataset: Dataset name (ignored).

        Returns:
            Tuple of (start_date, end_date) as strings, or (None, None) if empty.

        """
        return super().get_date_range()

    def list_sids(self, dataset: str) -> list[int]:  # type: ignore[override]
        """
        List unique security IDs (deprecated API).

        Args:
            dataset: Dataset name (ignored).

        Returns:
            Sorted list of unique security IDs.

        """
        return super().list_sids()


__all__ = ["AdjFactorStore", "StockAdjFactorStore"]
