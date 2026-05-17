"""
ParquetStore — year-partitioned Parquet data storage.

Implementation details are split into leaf modules:
- :mod:`parquet_paths` — path layout helpers
- :mod:`parquet_read`  — scan / filter / dedup
- :mod:`parquet_write` — merge / prepare / delete
- :mod:`parquet_metadata` — years / checksum / date-range
"""

from __future__ import annotations

import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import polars as pl

from ditto_platform.foundation import logger, traced
from ditto_platform.foundation.storage.parquet_metadata import (
    get_checksum as _get_checksum,
)
from ditto_platform.foundation.storage.parquet_metadata import (
    get_date_range as _get_date_range,
)
from ditto_platform.foundation.storage.parquet_metadata import (
    get_years as _get_years,
)
from ditto_platform.foundation.storage.parquet_metadata import (
    list_unique_values as _list_unique_values,
)
from ditto_platform.foundation.storage.parquet_paths import (
    collect_paths as _collect_paths,
)
from ditto_platform.foundation.storage.parquet_paths import (
    get_path as _get_path,
)
from ditto_platform.foundation.storage.parquet_read import (
    normalize_filters as _normalize_filters,
)
from ditto_platform.foundation.storage.parquet_read import (
    scan_parquet as _scan_parquet,
)
from ditto_platform.foundation.storage.parquet_write import (
    MergeResult,
)
from ditto_platform.foundation.storage.parquet_write import (
    delete_from_partition as _delete_from_partition,
)
from ditto_platform.foundation.storage.parquet_write import (
    merge_with_existing as _merge_with_existing,
)
from ditto_platform.foundation.storage.parquet_write import (
    prepare_for_write as _prepare_for_write,
)
from ditto_platform.foundation.storage.partition_strategy import (
    PartitionStrategy,
    YearlyPartition,
)
from ditto_platform.foundation.storage.types import OnDuplicate, WriteStoreResult
from ditto_platform.foundation.util.io import atomic_write, file_md5


class ParquetStore:
    """
    Parquet file storage implementation.

    Year-partitioned data storage: data_root/dataset/YYYY.parquet

    Attributes:
        data_root: Root directory path for data.

    """

    def __init__(
        self,
        data_root: Path,
        partition_strategy: PartitionStrategy = YearlyPartition(),
        key_columns: tuple[str, ...] = (),
        date_column: str | None = None,
        instrument_column: str | None = None,
    ) -> None:
        self._data_root = Path(data_root)
        self._partition = partition_strategy
        self._key_columns = tuple(key_columns)
        self._date_column = date_column
        self._instrument_column = instrument_column

    @property
    def data_root(self) -> Path:
        """Get root directory path for data."""
        return self._data_root

    # ============ Hook methods (can be overridden by subclasses) ============

    def _get_key_columns(self) -> list[str]:
        return list(self._key_columns)

    def _get_sort_columns(self) -> list[str]:
        return self._get_key_columns()

    def _get_date_column(self) -> str | None:
        return self._date_column

    def _require_date_column(self) -> str:
        date_column = self._get_date_column()
        if date_column is None:
            msg = "date_column is required for date-based operations"
            raise ValueError(msg)
        return date_column

    def _prepare_for_write(self, df: pl.DataFrame) -> pl.DataFrame:
        """Normalize date columns and sort. Subclasses may override for extra logic."""
        return _prepare_for_write(df, self._get_date_column(), self._get_sort_columns())

    def _merge_with_existing(
        self, df: pl.DataFrame, existing: pl.DataFrame, on_duplicate: OnDuplicate
    ) -> MergeResult:
        """Merge new data with existing. Subclasses may override for extra logic."""
        return _merge_with_existing(df, existing, self._get_key_columns(), on_duplicate)

    def _validate_data(self, df: pl.DataFrame) -> None:
        pass

    # ============ Path helpers (delegate to parquet_paths) ============

    def _get_path(self, dataset: str, partition_key: str) -> Path:
        return _get_path(self._data_root, dataset, partition_key, self._partition)

    def _collect_paths(
        self,
        dataset: str,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> list[Path]:
        return _collect_paths(
            self._data_root, dataset, self._partition, start_date, end_date
        )

    # ============ Read ============

    @traced("data.read")
    def read(
        self,
        dataset: str,
        start_date: str | None = None,
        end_date: str | None = None,
        filters: pl.Expr | Sequence[pl.Expr] | None = None,
    ) -> pl.DataFrame:
        """Read data with optional date range and expression filters."""
        start_time = time.time()

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

        str_paths = [str(p) for p in paths]
        result = _scan_parquet(
            str_paths,
            _normalize_filters(filters),
            start_date,
            end_date,
            self._require_date_column() if (start_date or end_date) else None,
            self._get_sort_columns(),
            self._get_key_columns(),
        )

        duration_ms = (time.time() - start_time) * 1000
        logger.info(
            "Data read completed",
            event="data_read_complete",
            dataset=dataset,
            start_date=start_date,
            end_date=end_date,
            row_count=len(result),
            duration_ms=round(duration_ms, 2),
        )
        return result

    # ============ Write ============

    @traced("data.write")
    def write(
        self,
        dataset: str,
        data: object,
        on_duplicate: str = "error",
        **kwargs: object,
    ) -> WriteStoreResult:
        """Write data with duplicate handling."""
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

        if len(df) == 0:
            return WriteStoreResult(
                file_path="", checksum="", added=0, updated=0, skipped=0, is_merge=False
            )

        self._validate_data(df)

        dataset_dir = self._data_root / dataset
        dataset_dir.mkdir(parents=True, exist_ok=True)

        file_path = self._get_path(dataset, str(year))
        is_merge = file_path.exists()
        strategy = OnDuplicate(on_duplicate)
        key_columns = self._get_key_columns()

        # Batch internal dedup
        if key_columns:
            batch_dup = (
                df.group_by(key_columns)
                .agg(pl.len().alias("_count"))
                .filter(pl.col("_count") > 1)
            )
            if not batch_dup.is_empty():
                logger.warning(
                    "Batch internal duplicates detected, auto-dedup (keep first)",
                    event="batch_internal_duplicates",
                    dataset=dataset,
                    year=year,
                    duplicate_count=len(batch_dup),
                )
                df = df.unique(subset=key_columns, keep="first")

        # Merge with existing
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

        df = self._prepare_for_write(df)
        atomic_write(df, file_path)
        checksum = file_md5(file_path)

        logger.info(
            "Data write completed",
            event="data_write_complete",
            dataset=dataset,
            year=year,
            row_count=len(df),
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

    # ============ Delete ============

    @traced("data.delete")
    def delete(
        self,
        dataset: str,
        start_date: str | None = None,
        end_date: str | None = None,
        filters: pl.Expr | Sequence[pl.Expr] | None = None,
    ) -> int:
        """Delete matching rows from a dataset."""
        paths = self._collect_paths(dataset, start_date, end_date)
        if not paths:
            return 0

        date_col = self._require_date_column() if start_date or end_date else ""
        normalized = _normalize_filters(filters)

        total_deleted = 0
        for path in paths:
            total_deleted += _delete_from_partition(
                path, normalized, date_col, start_date, end_date
            )
        return total_deleted

    # ============ Metadata ============

    def get_years(self, dataset: str) -> list[int]:
        """Get available years for a dataset."""
        return _get_years(self._data_root, dataset)

    def delete_partition(self, dataset: str, partition_key: str) -> bool:
        """Delete a partition by key."""
        path = self._get_path(dataset, partition_key)
        if path.exists():
            path.unlink()
            return True
        return False

    def get_checksum(self, dataset: str, partition_key: str) -> str:
        """Get MD5 checksum of a partition."""
        return _get_checksum(self._get_path(dataset, partition_key))

    def count(
        self,
        dataset: str,
        start_date: str | None = None,
        end_date: str | None = None,
        filters: pl.Expr | Sequence[pl.Expr] | None = None,
    ) -> int:
        """Count records in a dataset."""
        return len(
            self.read(
                dataset, start_date=start_date, end_date=end_date, filters=filters
            )
        )

    def get_date_range(self, dataset: str) -> tuple[str | None, str | None]:
        """Get overall date range for a dataset."""
        paths = self._collect_paths(dataset)
        date_col = self._get_date_column()
        if date_col is None:
            return None, None
        return _get_date_range(paths, date_col)

    def list_unique_values(self, dataset: str, column: str) -> list[Any]:
        """List unique values from a dataset column."""
        paths = self._collect_paths(dataset)
        return _list_unique_values(paths, column)
