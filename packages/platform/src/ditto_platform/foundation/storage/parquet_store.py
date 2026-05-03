"""
ParquetStore implementation for year-partitioned Parquet data storage.

This module provides a unified Parquet store implementation that supports:
- Year-partitioned data organization (data_root/dataset/YYYY.parquet)
- Configurable partition strategies via PartitionStrategy
- Duplicate data handling (error/keep_first/keep_last)
- Automatic deduplication (batch internal duplicates)
- Metadata operations:
  get_years, get_checksum, count, get_date_range, list_instrument_ids
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import polars as pl

from ditto_platform.foundation import Metrics, logger, traced
from ditto_platform.foundation.storage.partition_strategy import (
    PartitionStrategy,
    YearlyPartition,
)
from ditto_platform.foundation.storage.types import OnDuplicate, WriteStoreResult
from ditto_platform.foundation.util.io import atomic_write, file_md5


@dataclass(frozen=True)
class MergeResult:
    """Merge result."""

    df: pl.DataFrame
    added: int
    updated: int


class ParquetStore:
    """
    Parquet file storage implementation.

    Year-partitioned data storage: data_root/dataset/YYYY.parquet

    Supported features:
    - Year-partitioned storage (configurable via PartitionStrategy)
    - Date range queries
    - Duplicate data handling (error/keep_first/keep_last)
    - Automatic deduplication (batch internal duplicates)
    - Metadata operations (get_years, get_checksum, count, get_date_range,
      list_instrument_ids)

    Attributes:
        data_root: Root directory path for data.
        _partition: Partition strategy.

    """

    def __init__(
        self,
        data_root: Path,
        partition_strategy: PartitionStrategy = YearlyPartition(),
    ) -> None:
        """
        Initialize ParquetStore.

        Args:
            data_root: Root directory path for data.
            partition_strategy: Partition strategy, default yearly.

        """
        self._data_root = Path(data_root)
        self._partition = partition_strategy

    @property
    def data_root(self) -> Path:
        """Get root directory path for data."""
        return self._data_root

    # ============ Path operations ============

    def _get_path(self, dataset: str, partition_key: str) -> Path:
        """
        Get partition file path.

        Args:
            dataset: Dataset name.
            partition_key: Partition key.

        Returns:
            Parquet file path.

        """
        return self._data_root / dataset / self._partition.get_filename(partition_key)

    def _get_partition_key(self, date_str: str) -> str:
        """
        Extract partition key from date string.

        Args:
            date_str: Date string (YYYY-MM-DD).

        Returns:
            Partition key.

        """
        return self._partition.get_partition_key(date_str)

    def _collect_paths(
        self,
        dataset: str,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> list[Path]:
        """
        Collect partition file paths.

        Args:
            dataset: Dataset name.
            start_date: Start date (YYYY-MM-DD) (optional).
            end_date: End date (YYYY-MM-DD) (optional).

        Returns:
            List of file paths.

        """
        # Get partition keys to read
        partition_keys = self._partition.get_partitions_from_filters(
            start_date, end_date
        )

        if not partition_keys:
            # No filters, scan all files
            dataset_dir = self._data_root / dataset
            if not dataset_dir.exists():
                return []
            return sorted(dataset_dir.glob("*.parquet"))

        # Only read specified partitions
        paths: list[Path] = []
        for key in partition_keys:
            path = self._get_path(dataset, key)
            if path.exists():
                paths.append(path)
        return sorted(paths)

    # ============ Hook methods (can be overridden by wrapper classes) ============

    def _get_key_columns(self) -> list[str]:
        """
        Get unique key column names (for deduplication).

        Returns:
            Key column names.

        """
        return ["instrument_id", "trade_date"]

    def _get_sort_columns(self) -> list[str]:
        """
        Get sort column names (defaults to key columns).

        Returns:
            Sort column names.

        """
        return self._get_key_columns()

    def _get_date_column(self) -> str:
        """
        Get date column name (default trade_date).

        Returns:
            Date column name.

        """
        return "trade_date"

    def _validate_data(self, df: pl.DataFrame) -> None:
        """
        Validate data (subclasses can override).

        Args:
            df: Data to validate.

        Raises:
            ValueError: If data validation fails.

        """
        # Default: no validation, subclasses can override
        pass

    # ============ Read operation ============

    @traced("data.read")
    def read(
        self,
        dataset: str,
        instrument_ids: list[int] | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        **kwargs: object,
    ) -> pl.DataFrame:
        """
        Read data.

        Args:
            dataset: Dataset name.
            instrument_ids: Instrument ID list (optional).
            start_date: Start date (YYYY-MM-DD) (optional).
            end_date: End date (YYYY-MM-DD) (optional).
            **kwargs: Other parameters (ignored).

        Returns:
            DataFrame with matching records.

        """
        start_time = time.time()

        # Collect all relevant partition files
        paths = self._collect_paths(dataset, start_date, end_date)

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

        # Use scan_parquet for predicate pushdown
        lf = pl.scan_parquet([str(p) for p in paths])

        # Apply filters
        if instrument_ids:
            lf = lf.filter(pl.col("instrument_id").is_in(instrument_ids))

        date_col = self._get_date_column()
        if start_date:
            # Convert string to literal date
            start_dt = datetime.strptime(start_date, "%Y-%m-%d").date()
            lf = lf.filter(pl.col(date_col) >= pl.lit(start_dt))

        if end_date:
            end_dt = datetime.strptime(end_date, "%Y-%m-%d").date()
            lf = lf.filter(pl.col(date_col) <= pl.lit(end_dt))

        # Ensure sorting for correct unique(keep="last") and result order
        sort_cols = self._get_sort_columns()
        result = (
            lf.sort(sort_cols)
            .unique(subset=self._get_key_columns(), keep="last")
            .sort(sort_cols)
            .collect()
        )

        duration_ms = (time.time() - start_time) * 1000

        logger.info(
            "Data read completed",
            event="data_read_complete",
            dataset=dataset,
            start_date=start_date,
            end_date=end_date,
            sids_count=len(instrument_ids) if instrument_ids else None,
            row_count=len(result),
            duration_ms=round(duration_ms, 2),
        )

        # Record metrics
        Metrics.data_records.add(len(result), {"dataset": dataset, "status": "success"})
        Metrics.data_update_duration.record(duration_ms / 1000, {"dataset": dataset})

        return result

    # ============ Write operation ============

    def _prepare_for_write(self, df: pl.DataFrame) -> pl.DataFrame:
        """
        Prepare for write: normalize date columns and sort.

        Args:
            df: Input DataFrame.

        Returns:
            Prepared DataFrame.

        """
        date_col = self._get_date_column()
        if date_col in df.columns:
            if df[date_col].dtype == pl.String:
                df = df.with_columns(pl.col(date_col).str.strptime(pl.Date, "%Y-%m-%d"))
            elif df[date_col].dtype != pl.Date:
                df = df.with_columns(pl.col(date_col).cast(pl.Date))

        sort_cols = self._get_sort_columns()
        return df.sort(sort_cols)

    def _merge_with_existing(
        self,
        df: pl.DataFrame,
        existing: pl.DataFrame,
        on_duplicate: OnDuplicate,
    ) -> MergeResult:
        """
        Merge new data with existing data.

        Args:
            df: New data.
            existing: Existing data.
            on_duplicate: Duplicate data handling strategy.

        Returns:
            MergeResult with merged DataFrame and statistics.

        Raises:
            ValueError: If on_duplicate=ERROR and duplicate data exists.

        """
        key_columns = self._get_key_columns()

        # Detect duplicate data
        existing_keys = existing.select(key_columns)
        new_keys = df.select(key_columns)

        # Find overlapping keys
        merged_keys = existing_keys.join(new_keys, on=key_columns, how="inner")
        overlap_count = len(merged_keys)

        if not merged_keys.is_empty():
            # Duplicate data exists
            if on_duplicate == OnDuplicate.ERROR:
                msg = (
                    f"Duplicate data: {overlap_count} overlapping key pairs. "
                    "Use OnDuplicate.KEEP_FIRST to preserve, or "
                    "OnDuplicate.KEEP_LAST to overwrite."
                )
                raise ValueError(msg)
            elif on_duplicate == OnDuplicate.KEEP_FIRST:
                # Keep existing data, filter out duplicates in new data
                non_overlapping = new_keys.join(
                    existing_keys, on=key_columns, how="anti"
                )
                df = df.join(non_overlapping, on=key_columns, how="inner")
                combined = pl.concat([existing, df])
                added = len(df)
                updated = 0
            elif on_duplicate == OnDuplicate.KEEP_LAST:
                # Last-Write-Wins: new data overwrites existing
                combined = pl.concat([existing, df])
                combined = combined.unique(subset=key_columns, keep="last")
                added = len(df) - overlap_count
                updated = overlap_count
            else:
                msg = f"Unknown OnDuplicate strategy: {on_duplicate}"
                raise ValueError(msg)
        else:
            # No duplicates, merge directly
            combined = pl.concat([existing, df])
            added = len(df)
            updated = 0

        return MergeResult(df=combined, added=added, updated=updated)

    @traced("data.write")
    def write(
        self,
        dataset: str,
        data: object,
        on_duplicate: str = "error",
        **kwargs: object,
    ) -> WriteStoreResult:
        """
        Write data.

        Args:
            dataset: Dataset name.
            data: Data to write (pl.DataFrame).
            on_duplicate: Duplicate data handling strategy
                ("error"|"keep_first"|"keep_last").
            **kwargs: Other parameters, must include year.

        Returns:
            Write result statistics.

        Raises:
            ValueError: If data is not a DataFrame or missing year parameter.

        """
        if not isinstance(data, pl.DataFrame):
            msg = "data must be a polars DataFrame"
            raise ValueError(msg)

        year = kwargs.get("year")
        if year is None:
            msg = "year parameter is required"
            raise ValueError(msg)

        if not isinstance(year, int):
            msg = "year must be an integer"
            raise ValueError(msg)

        df: pl.DataFrame = data

        # Empty data: return immediately
        if len(df) == 0:
            return WriteStoreResult(
                file_path="",
                checksum="",
                added=0,
                updated=0,
                skipped=0,
                is_merge=False,
            )

        # Validate data (subclasses can override)
        self._validate_data(df)

        # Ensure directory exists
        dataset_dir = self._data_root / dataset
        dataset_dir.mkdir(parents=True, exist_ok=True)

        file_path = self._get_path(dataset, str(year))
        is_merge = file_path.exists()

        # Parse dedup strategy
        strategy = OnDuplicate(on_duplicate)

        # Detect batch internal duplicates and auto-dedup
        key_columns = self._get_key_columns()
        batch_duplicates = (
            df.group_by(key_columns)
            .agg(pl.len().alias("_count"))
            .filter(pl.col("_count") > 1)
        )

        if not batch_duplicates.is_empty():
            logger.warning(
                "Batch internal duplicates detected, auto-dedup (keep first)",
                event="batch_internal_duplicates",
                dataset=dataset,
                year=year,
                duplicate_count=len(batch_duplicates),
            )
            df = df.unique(subset=key_columns, keep="first")

        # Merge with existing data and get statistics
        added = 0
        updated = 0
        if is_merge:
            existing = pl.read_parquet(file_path)
            merge_result = self._merge_with_existing(df, existing, strategy)
            df = merge_result.df
            added = merge_result.added
            updated = merge_result.updated
        else:
            added = len(df)
            updated = 0

        # Prepare for write
        df = self._prepare_for_write(df)

        # Atomic write
        atomic_write(df, file_path)

        # Compute checksum
        checksum = file_md5(file_path)

        logger.info(
            "Data write completed",
            event="data_write_complete",
            dataset=dataset,
            year=year,
            row_count=len(df),
            total_rows=len(df),
            is_merge=is_merge,
            file_path=str(file_path),
            checksum=checksum,
        )

        return WriteStoreResult(
            file_path=str(file_path),
            checksum=checksum,
            added=added,
            updated=updated,
            skipped=0,
            is_merge=is_merge,
        )

    # ============ Delete operation ============

    @traced("data.delete")
    def delete(
        self,
        dataset: str,
        instrument_ids: list[int] | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        **kwargs: object,
    ) -> int:
        """
        Delete data.

        Args:
            dataset: Dataset name.
            instrument_ids: Instrument ID list (optional).
            start_date: Start date (YYYY-MM-DD) (optional).
            end_date: End date (YYYY-MM-DD) (optional).
            **kwargs: Other parameters (ignored).

        Returns:
            Number of deleted records.

        """
        # Collect all relevant partition files
        paths = self._collect_paths(dataset, start_date, end_date)

        if not paths:
            return 0

        total_deleted = 0
        date_col = self._get_date_column()

        for path in paths:
            # Read existing data
            df = pl.read_parquet(path)

            # Count before deletion
            original_count = len(df)

            # Build delete condition: keep data NOT in delete range
            keep_mask = pl.lit(True)

            if instrument_ids:
                # Delete specified instrument_id: keep data NOT in instrument_ids
                keep_mask = keep_mask & ~pl.col("instrument_id").is_in(instrument_ids)

            if start_date and end_date:
                # Delete data in date range: keep data NOT in range
                in_range = (
                    pl.col(date_col)
                    >= pl.lit(start_date).str.strptime(pl.Date, "%Y-%m-%d")
                ) & (
                    pl.col(date_col)
                    <= pl.lit(end_date).str.strptime(pl.Date, "%Y-%m-%d")
                )
                keep_mask = keep_mask & ~in_range
            elif start_date:
                # Only delete data after start_date
                keep_mask = keep_mask & ~(
                    pl.col(date_col)
                    >= pl.lit(start_date).str.strptime(pl.Date, "%Y-%m-%d")
                )
            elif end_date:
                # Only delete data before end_date
                keep_mask = keep_mask & ~(
                    pl.col(date_col)
                    <= pl.lit(end_date).str.strptime(pl.Date, "%Y-%m-%d")
                )

            # Apply filter (keep data NOT matching delete conditions)
            df = df.filter(keep_mask)

            # Count deleted
            deleted_count = original_count - len(df)
            total_deleted += deleted_count

            # Write back
            if len(df) > 0:
                atomic_write(df, path)
            else:
                # If empty, delete file
                path.unlink()

        return total_deleted

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

    def delete_partition(self, dataset: str, partition_key: str) -> bool:
        """
        Delete a partition by key.

        Args:
            dataset: Dataset name.
            partition_key: Partition key (e.g., year "2024").

        Returns:
            True if deleted, False if file didn't exist.

        """
        path = self._get_path(dataset, partition_key)
        if path.exists():
            path.unlink()
            return True
        return False

    def get_checksum(self, dataset: str, partition_key: str) -> str:
        """
        Get MD5 checksum of a partition.

        Args:
            dataset: Dataset name.
            partition_key: Partition key (e.g., year "2024").

        Returns:
            Checksum hex string, or empty string if file doesn't exist.

        """
        path = self._get_path(dataset, partition_key)
        if path.exists():
            result: str = file_md5(path)
            return result
        return ""

    def count(
        self,
        dataset: str,
        instrument_ids: list[int] | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> int:
        """
        Count records in a dataset.

        Args:
            dataset: Dataset name.
            instrument_ids: Filter by instrument IDs.
            start_date: Start date (YYYY-MM-DD).
            end_date: End date (YYYY-MM-DD).

        Returns:
            Number of matching records.

        """
        df = self.read(
            dataset,
            instrument_ids=instrument_ids,
            start_date=start_date,
            end_date=end_date,
        )
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
        paths = self._collect_paths(dataset)
        if not paths:
            return None, None

        lf = pl.scan_parquet([str(p) for p in paths])
        date_col = self._get_date_column()
        min_max = lf.select(
            [
                pl.col(date_col).min().alias("min"),
                pl.col(date_col).max().alias("max"),
            ]
        ).collect()

        if len(min_max) == 0 or min_max["min"][0] is None:
            return None, None

        return str(min_max["min"][0]), str(min_max["max"][0])

    def list_instrument_ids(self, dataset: str) -> list[int]:
        """
        List unique instrument IDs in a dataset.

        Args:
            dataset: Dataset name.

        Returns:
            Sorted list of unique instrument IDs.

        """
        years = self.get_years(dataset)
        if not years:
            return []

        paths = self._collect_paths(dataset)
        if not paths:
            return []

        lf = pl.scan_parquet([str(p) for p in paths])
        result = lf.select(pl.col("instrument_id").unique()).collect()

        instrument_ids: list[int] = result["instrument_id"].to_list()
        return instrument_ids
