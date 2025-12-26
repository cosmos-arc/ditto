"""
Adjustment factor storage with year partitioning.

Stores price adjustment factors for dividend/split/bonus events in Parquet files
with year partitioning. Following design document at docs/design/02_data_design.md.
"""

from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path
from typing import Any

import polars as pl
from ditto_foundation import M, logger, span, traced
from ditto_foundation.util.io import atomic_write, file_md5


class AdjFactorStore:
    """
    Adjustment factor data storage with year partitioning.

    Storage structure:
        data_root/
            adj_factor/
                2020.parquet
                2021.parquet
                ...
    """

    def __init__(self, data_root: Path) -> None:
        """
        Initialize AdjFactorStore.

        Args:
            data_root: Root directory for data storage.

        """
        self._data_root = Path(data_root)

    def _get_path(self, dataset: str, year: int) -> Path:
        """
        Get year partition file path.

        Args:
            dataset: Dataset name (e.g., "adj_factor").
            year: Year partition.

        Returns:
            Path to the Parquet file.

        """
        return self._data_root / dataset / f"{year}.parquet"

    def _collect_paths(
        self,
        dataset: str,
        start_year: int,
        end_year: int,
    ) -> list[Path]:
        """
        Collect year partition file paths.

        Args:
            dataset: Dataset name.
            start_year: Start year (inclusive).
            end_year: End year (inclusive).

        Returns:
            List of existing file paths.

        """
        dataset_dir = self._data_root / dataset
        if not dataset_dir.exists():
            return []

        paths: list[Path] = []
        for year in range(start_year, end_year + 1):
            path = dataset_dir / f"{year}.parquet"
            if path.exists():
                paths.append(path)

        return paths

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
        Read adjustment factor data.

        Args:
            dataset: Dataset name (e.g., "adj_factor").
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

    # ============ Write operations ============

    def write(
        self,
        dataset: str,
        df: pl.DataFrame,
        year: int,
    ) -> tuple[str, str]:
        """
        Write year partition file.

        Strategy: Read existing data → Merge deduplicate → Atomic write.

        Args:
            dataset: Dataset name.
            df: Data to write.
            year: Year partition.

        Returns:
            Tuple of (file_path, checksum).

        """
        with span("data.write", dataset=dataset, year=year) as s:
            return self._write_impl(dataset, df, year, s)

    def _write_impl(
        self,
        dataset: str,
        df: pl.DataFrame,
        year: int,
        span_ctx: Any,
    ) -> tuple[str, str]:
        start_time = time.time()

        dataset_dir = self._data_root / dataset
        dataset_dir.mkdir(parents=True, exist_ok=True)

        file_path = self._get_path(dataset, year)
        is_merge = file_path.exists()

        # Merge with existing data
        if file_path.exists():
            existing = pl.read_parquet(file_path)
            combined = pl.concat([existing, df]).unique(
                subset=["sid", "trade_date"],
                keep="last",  # New data overwrites
            )
        else:
            combined = df

        # Sort for optimal read performance AND correct last() aggregation
        combined = combined.sort(["sid", "trade_date"])

        # Atomic write
        atomic_write(combined, file_path)

        # Calculate checksum
        checksum: str = file_md5(file_path)

        duration_ms = (time.time() - start_time) * 1000

        # Set span attributes
        if span_ctx:
            span_ctx.set_attribute("row_count", len(df))
            span_ctx.set_attribute("total_rows", len(combined))
            span_ctx.set_attribute("is_merge", is_merge)

        logger.info(
            "Data write completed",
            event="data_write_complete",
            dataset=dataset,
            year=year,
            row_count=len(df),
            total_rows=len(combined),
            is_merge=is_merge,
            file_path=str(file_path),
            checksum=checksum,
            duration_ms=round(duration_ms, 2),
        )

        # Record metrics
        M.data_records.add(len(df), {"dataset": dataset, "status": "success"})
        M.data_update_duration.record(duration_ms / 1000, {"dataset": dataset})

        return str(file_path), checksum

    # ============ Metadata operations ============

    def get_years(self, dataset: str) -> list[int]:
        """
        Get available years for a dataset.

        Args:
            dataset: Dataset name.

        Returns:
            Sorted list of available years.

        """
        dataset_dir = self._data_root / dataset
        if not dataset_dir.exists():
            return []

        years: list[int] = []
        for f in dataset_dir.glob("*.parquet"):
            try:
                year = int(f.stem)
                years.append(year)
            except ValueError:
                # Skip files that don't match year pattern
                continue

        return sorted(years)

    def delete(self, dataset: str, year: int) -> bool:
        """
        Delete a year partition.

        Args:
            dataset: Dataset name.
            year: Year partition to delete.

        Returns:
            True if deleted, False if file didn't exist.

        """
        path = self._get_path(dataset, year)
        if path.exists():
            path.unlink()
            return True
        return False

    def get_checksum(self, dataset: str, year: int) -> str:
        """
        Get MD5 checksum of a year partition.

        Args:
            dataset: Dataset name.
            year: Year partition.

        Returns:
            Checksum hex string, or empty string if file doesn't exist.

        """
        path = self._get_path(dataset, year)
        if path.exists():
            result: str = file_md5(path)
            return result
        return ""

    def count(
        self,
        dataset: str,
        sids: list[int] | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> int:
        """
        Count records in a dataset.

        Args:
            dataset: Dataset name.
            sids: Filter by security IDs.
            start_date: Start date (YYYY-MM-DD).
            end_date: End date (YYYY-MM-DD).

        Returns:
            Number of matching records.

        """
        df = self.read(dataset, sids=sids, start_date=start_date, end_date=end_date)
        return len(df)

    def get_date_range(self, dataset: str) -> tuple[str | None, str | None]:
        """
        Get overall date range for a dataset.

        Args:
            dataset: Dataset name.

        Returns:
            Tuple of (start_date, end_date) as strings, or (None, None) if empty.

        """
        years = self.get_years(dataset)
        if not years:
            return None, None

        # Scan all partitions and find min/max dates
        paths = self._collect_paths(dataset, min(years), max(years))
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
        List unique security IDs in a dataset.

        Args:
            dataset: Dataset name.

        Returns:
            Sorted list of unique security IDs.

        """
        years = self.get_years(dataset)
        if not years:
            return []

        paths = self._collect_paths(dataset, min(years), max(years))
        if not paths:
            return []

        lf = pl.scan_parquet([str(p) for p in paths])
        result = lf.select(pl.col("sid").unique()).collect()

        sids: list[int] = result["sid"].to_list()
        return sids
