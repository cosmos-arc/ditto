"""
Base class for year-partitioned Parquet data stores (B.4).

Provides common functionality for stores that organize data in Parquet files
with year partitioning (e.g., data_root/dataset/YYYY.parquet).

Following design document at docs/design/02_data_design.md.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

import polars as pl
from ditto_foundation import logger, traced
from ditto_foundation.util.io import atomic_write, file_md5

from ditto_datahub.types import OnDuplicate
from ditto_datahub.types import WriteResultStore as WriteResult


@dataclass(frozen=True)
class MergeResult:
    """合并结果"""

    df: pl.DataFrame
    added: int
    updated: int


class ParquetStoreBase(ABC):
    """
    Base class for year-partitioned Parquet data stores.

    Storage structure:
        data_root/
            dataset/
                2020.parquet
                2021.parquet
                ...

    Subclasses must implement read() and write() methods with their
    specific logic while inheriting common metadata operations.
    """

    def __init__(self, data_root: Path) -> None:
        """
        Initialize ParquetStoreBase.

        Args:
            data_root: Root directory for data storage.

        """
        self._data_root = Path(data_root)

    # ============ Public properties ============

    @property
    def data_root(self) -> Path:
        """Get the data root directory."""
        return self._data_root

    # ============ Path operations ============

    def _get_path(self, dataset: str, year: int) -> Path:
        """
        Get year partition file path.

        Args:
            dataset: Dataset name (e.g., "stock_daily", "adj_factor").
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

    # ============ Abstract methods (must be implemented by subclasses) ============

    @abstractmethod
    def _get_key_columns(self) -> list[str]:
        """
        获取唯一键列名（用于去重）。

        Returns:
            键列名列表。

        """
        ...

    @abstractmethod
    def read(
        self,
        dataset: str,
        sids: list[int] | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        """
        Read data from the store.

        Args:
            dataset: Dataset name.
            sids: Filter by security IDs.
            start_date: Start date (YYYY-MM-DD).
            end_date: End date (YYYY-MM-DD).

        Returns:
            DataFrame with matching records.

        """
        ...

    def _get_sort_columns(self) -> list[str]:
        """
        获取排序列名（默认为键列）。

        Returns:
            排序列名列表。

        """
        return self._get_key_columns()

    def _get_date_column(self) -> str:
        """
        获取日期列名（默认 trade_date）。

        Returns:
            日期列名。

        """
        return "trade_date"

    def _prepare_for_write(self, df: pl.DataFrame) -> pl.DataFrame:
        """
        准备写入：归一化日期列并排序。

        Args:
            df: 输入 DataFrame。

        Returns:
            准备好的 DataFrame。

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
        file_path: Path,
        on_duplicate: OnDuplicate,
    ) -> MergeResult:
        """
        合并新数据与现有数据。

        Args:
            df: 新数据。
            file_path: 现有数据文件路径。
            on_duplicate: 重复数据处理策略。

        Returns:
            MergeResult 包含合并后的 DataFrame 和统计信息。

        Raises:
            ValueError: 如果 on_duplicate=ERROR 且存在重复数据。

        """
        if file_path.exists():
            existing = pl.read_parquet(file_path)
            key_columns = self._get_key_columns()

            # 检测重复数据
            existing_keys = existing.select(key_columns)
            new_keys = df.select(key_columns)

            # 找出重叠的键
            merged_keys = existing_keys.join(new_keys, on=key_columns, how="inner")
            overlap_count = len(merged_keys)

            if not merged_keys.is_empty():
                # 存在重复数据
                if on_duplicate == OnDuplicate.ERROR:
                    dup_count = overlap_count
                    msg = (
                        f"Duplicate data: {dup_count} overlapping key pairs. "
                        "Use OnDuplicate.KEEP_FIRST to preserve, or "
                        "OnDuplicate.KEEP_LAST to overwrite."
                    )
                    raise ValueError(msg)
                elif on_duplicate == OnDuplicate.KEEP_FIRST:
                    # 保留现有数据，过滤掉新数据中的重复部分
                    non_overlapping = new_keys.join(
                        existing_keys, on=key_columns, how="anti"
                    )
                    df = df.join(non_overlapping, on=key_columns, how="inner")
                    combined = pl.concat([existing, df])
                    # added = 新数据中去重后的行数
                    added = len(df)
                    updated = 0
                elif on_duplicate == OnDuplicate.KEEP_LAST:
                    # Last-Write-Wins: 新数据覆盖现有数据
                    combined = pl.concat([existing, df])
                    combined = combined.unique(subset=key_columns, keep="last")
                    # added = 新数据中非重叠的行数
                    added = len(df) - overlap_count
                    # updated = 重叠的行数
                    updated = overlap_count
                else:
                    raise ValueError(f"Unknown OnDuplicate strategy: {on_duplicate}")
            else:
                # 无重复，直接合并
                combined = pl.concat([existing, df])
                added = len(df)
                updated = 0
        else:
            combined = df
            added = len(df)
            updated = 0

        return MergeResult(df=combined, added=added, updated=updated)

    @traced("data.write")
    def write(
        self,
        dataset: str,
        df: pl.DataFrame,
        year: int,
        on_duplicate: OnDuplicate = OnDuplicate.ERROR,
    ) -> WriteResult:
        """
        统一的写入实现（所有子类共享）。

        Args:
            dataset: 数据集名称。
            df: 要写入的数据。
            year: 年份分区。
            on_duplicate: 重复数据处理策略。

        Returns:
            写入结果统计。

        """
        if len(df) == 0:
            return WriteResult(
                file_path="",
                checksum="",
                added=0,
                updated=0,
                skipped=0,
                is_merge=False,
            )

        # 确保目录存在
        dataset_dir = self._data_root / dataset
        dataset_dir.mkdir(parents=True, exist_ok=True)

        file_path = self._get_path(dataset, year)
        is_merge = file_path.exists()

        # 检测 batch 内部重复并自动去重
        key_columns = self._get_key_columns()
        batch_duplicates = (
            df.group_by(key_columns)
            .agg(pl.len().alias("_count"))
            .filter(pl.col("_count") > 1)
        )

        if not batch_duplicates.is_empty():
            logger.warning(
                "检测到 batch 内部重复, 自动去重(保留第一条)",
                event="batch_internal_duplicates",
                dataset=dataset,
                year=year,
                duplicate_count=len(batch_duplicates),
            )
            df = df.unique(subset=key_columns, keep="first")

        # 合并现有数据并获取统计信息
        merge_result = self._merge_with_existing(df, file_path, on_duplicate)
        combined = merge_result.df

        # 准备写入
        combined = self._prepare_for_write(combined)

        # 使用合并结果中的统计信息
        added = merge_result.added
        updated = merge_result.updated
        skipped = 0

        # Atomic 写入
        atomic_write(combined, file_path)

        # 计算 checksum
        checksum = file_md5(file_path)

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
        )

        return WriteResult(
            file_path=str(file_path),
            checksum=checksum,
            added=added,
            updated=updated,
            skipped=skipped,
            is_merge=is_merge,
        )

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
