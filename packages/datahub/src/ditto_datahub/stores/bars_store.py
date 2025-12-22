"""
Market bars storage with year partitioning.

Stores market daily data (stock/ETF) in Parquet files with year partitioning.
Following design document at docs/design/02_data_design.md.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import polars as pl
from ditto_foundation.util.io import atomic_write, file_md5


class BarsStore:
    """
    Market bars data storage with year partitioning.

    Storage structure:
        data_root/
            market_daily/
                2020.parquet
                2021.parquet
                ...
            etf_daily/
                2020.parquet
                ...
    """

    def __init__(self, data_root: Path) -> None:
        """
        Initialize BarsStore.

        Args:
            data_root: Root directory for data storage.

        """
        self._data_root = Path(data_root)

    def _get_path(self, dataset: str, year: int) -> Path:
        """
        Get year partition file path.

        Args:
            dataset: Dataset name (e.g., "market_daily", "etf_daily").
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

    def read(
        self,
        dataset: str,
        sids: list[int] | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        """
        Read market bars data.

        Args:
            dataset: Dataset name (e.g., "market_daily", "etf_daily").
            sids: Filter by security IDs.
            start_date: Start date (YYYY-MM-DD).
            end_date: End date (YYYY-MM-DD).

        Returns:
            DataFrame with matching records.

        """
        # Determine year range from date filters
        start_year = int(start_date[:4]) if start_date else 1990
        end_year = int(end_date[:4]) if end_date else 2099

        paths = self._collect_paths(dataset, start_year, end_year)

        if not paths:
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

        return lf.unique(subset=["sid", "trade_date"], keep="last").collect()

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
        dataset_dir = self._data_root / dataset
        dataset_dir.mkdir(parents=True, exist_ok=True)

        file_path = self._get_path(dataset, year)

        # Merge with existing data
        if file_path.exists():
            existing = pl.read_parquet(file_path)
            combined = pl.concat([existing, df]).unique(
                subset=["sid", "trade_date"],
                keep="last",  # New data overwrites
            )
        else:
            combined = df

        # Sort for optimal read performance
        combined = combined.sort(["trade_date", "sid"])

        # Atomic write
        atomic_write(combined, file_path)

        # Calculate checksum
        checksum: str = file_md5(file_path)

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
