"""
ParquetStore implementation for year-partitioned Parquet data storage.

This module provides a unified Parquet store implementation that supports:
- Year-partitioned data organization (data_root/dataset/YYYY.parquet)
- Configurable partition strategies via PartitionStrategy
- Duplicate data handling (error/keep_first/keep_last)
- Automatic deduplication (batch internal duplicates)
- Metadata operations:
  get_years, get_checksum, count, get_date_range, list_instrument_ids

Following design document at docs/design/02_data_design.md.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import polars as pl
from ditto_infra.foundation import Metrics, logger, traced
from ditto_infra.foundation.util.io import atomic_write, file_md5

from ditto_data.models import OnDuplicate
from ditto_data.models.storage import WriteStoreResult as WriteResult
from ditto_data.storage.base.partition_strategy import (
    PartitionStrategy,
    YearlyPartition,
)


@dataclass(frozen=True)
class MergeResult:
    """合并结果"""

    df: pl.DataFrame
    added: int
    updated: int


class ParquetStore:
    """
    Parquet 文件存储实现.

    按年分区存储数据：data_root/dataset/YYYY.parquet

    支持特性：
    - 按年分区存储（可配置 PartitionStrategy）
    - 日期范围查询
    - 重复数据处理（error/keep_first/keep_last）
    - 自动去重（batch 内部重复）
    - 元数据操作（get_years, get_checksum, count, get_date_range, list_instrument_ids）

    Attributes:
        data_root: 数据根目录路径.
        _partition: 分区策略.

    """

    def __init__(
        self,
        data_root: Path,
        partition_strategy: PartitionStrategy = YearlyPartition(),
    ) -> None:
        """
        初始化 ParquetStore.

        Args:
            data_root: 数据根目录路径.
            partition_strategy: 分区策略，默认按年分区.

        """
        self._data_root = Path(data_root)
        self._partition = partition_strategy

    @property
    def data_root(self) -> Path:
        """获取数据根目录路径."""
        return self._data_root

    # ============ Path operations ============

    def _get_path(self, dataset: str, partition_key: str) -> Path:
        """
        获取分区文件路径.

        Args:
            dataset: 数据集名称.
            partition_key: 分区键.

        Returns:
            Parquet 文件路径.

        """
        return self._data_root / dataset / self._partition.get_filename(partition_key)

    def _get_partition_key(self, date_str: str) -> str:
        """
        从日期字符串提取分区键.

        Args:
            date_str: 日期字符串 (YYYY-MM-DD).

        Returns:
            分区键.

        """
        return self._partition.get_partition_key(date_str)

    def _collect_paths(
        self,
        dataset: str,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> list[Path]:
        """
        收集分区文件路径.

        Args:
            dataset: 数据集名称.
            start_date: 起始日期 (YYYY-MM-DD)（可选）.
            end_date: 结束日期 (YYYY-MM-DD)（可选）.

        Returns:
            文件路径列表.

        """
        # 获取需要读取的分区键
        partition_keys = self._partition.get_partitions_from_filters(
            start_date, end_date
        )

        if not partition_keys:
            # 无过滤条件，扫描所有文件
            dataset_dir = self._data_root / dataset
            if not dataset_dir.exists():
                return []
            return sorted(dataset_dir.glob("*.parquet"))

        # 只读取指定分区
        paths: list[Path] = []
        for key in partition_keys:
            path = self._get_path(dataset, key)
            if path.exists():
                paths.append(path)
        return sorted(paths)

    # ============ Hook methods (can be overridden by wrapper classes) ============

    def _get_key_columns(self) -> list[str]:
        """
        获取唯一键列名（用于去重）.

        Returns:
            键列名列表.

        """
        return ["instrument_id", "trade_date"]

    def _get_sort_columns(self) -> list[str]:
        """
        获取排序列名（默认为键列）.

        Returns:
            排序列名列表.

        """
        return self._get_key_columns()

    def _get_date_column(self) -> str:
        """
        获取日期列名（默认 trade_date）.

        Returns:
            日期列名.

        """
        return "trade_date"

    def _validate_data(self, df: pl.DataFrame) -> None:
        """
        验证数据（子类可重写）.

        Args:
            df: 要验证的数据.

        Raises:
            ValueError: 如果数据验证失败.

        """
        # 默认不做任何验证，子类可以重写
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
        读取数据.

        Args:
            dataset: 数据集名称.
            instrument_ids: 证券 ID 列表（可选）.
            start_date: 起始日期 (YYYY-MM-DD)（可选）.
            end_date: 结束日期 (YYYY-MM-DD)（可选）.
            **kwargs: 其他参数（忽略）.

        Returns:
            DataFrame 包含匹配的记录.

        """
        start_time = time.time()

        # 收集所有相关分区文件
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

        # 使用 scan_parquet 实现谓词下推
        lf = pl.scan_parquet([str(p) for p in paths])

        # 应用过滤条件
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
        准备写入：归一化日期列并排序.

        Args:
            df: 输入 DataFrame.

        Returns:
            准备好的 DataFrame.

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
        合并新数据与现有数据.

        Args:
            df: 新数据.
            existing: 现有数据.
            on_duplicate: 重复数据处理策略.

        Returns:
            MergeResult 包含合并后的 DataFrame 和统计信息.

        Raises:
            ValueError: 如果 on_duplicate=ERROR 且存在重复数据.

        """
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
                msg = (
                    f"Duplicate data: {overlap_count} overlapping key pairs. "
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
                added = len(df)
                updated = 0
            elif on_duplicate == OnDuplicate.KEEP_LAST:
                # Last-Write-Wins: 新数据覆盖现有数据
                combined = pl.concat([existing, df])
                combined = combined.unique(subset=key_columns, keep="last")
                added = len(df) - overlap_count
                updated = overlap_count
            else:
                msg = f"Unknown OnDuplicate strategy: {on_duplicate}"
                raise ValueError(msg)
        else:
            # 无重复，直接合并
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
    ) -> WriteResult:
        """
        写入数据.

        Args:
            dataset: 数据集名称.
            data: 要写入的数据（pl.DataFrame）.
            on_duplicate: 重复数据处理策略 ("error"|"keep_first"|"keep_last").
            **kwargs: 其他参数，必须包含 year.

        Returns:
            写入结果统计.

        Raises:
            ValueError: 如果 data 不是 DataFrame 或缺少 year 参数.

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

        # 空数据直接返回
        if len(df) == 0:
            return WriteResult(
                file_path="",
                checksum="",
                added=0,
                updated=0,
                skipped=0,
                is_merge=False,
            )

        # 验证数据（子类可重写）
        self._validate_data(df)

        # 确保目录存在
        dataset_dir = self._data_root / dataset
        dataset_dir.mkdir(parents=True, exist_ok=True)

        file_path = self._get_path(dataset, str(year))
        is_merge = file_path.exists()

        # 解析去重策略
        strategy = OnDuplicate(on_duplicate)

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

        # 准备写入
        df = self._prepare_for_write(df)

        # 原子写入
        atomic_write(df, file_path)

        # 计算 checksum
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

        return WriteResult(
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
        删除数据.

        Args:
            dataset: 数据集名称.
            instrument_ids: 证券 ID 列表（可选）.
            start_date: 起始日期 (YYYY-MM-DD)（可选）.
            end_date: 结束日期 (YYYY-MM-DD)（可选）.
            **kwargs: 其他参数（忽略）.

        Returns:
            删除的记录数.

        """
        # 收集所有相关分区文件
        paths = self._collect_paths(dataset, start_date, end_date)

        if not paths:
            return 0

        total_deleted = 0
        date_col = self._get_date_column()

        for path in paths:
            # 读取现有数据
            df = pl.read_parquet(path)

            # 计算删除前的行数
            original_count = len(df)

            # 构建删除条件：保留不在删除范围内的数据
            keep_mask = pl.lit(True)

            if instrument_ids:
                # 删除指定 instrument_id：保留不在 instrument_ids 中的数据
                keep_mask = keep_mask & ~pl.col("instrument_id").is_in(instrument_ids)

            if start_date and end_date:
                # 删除日期范围内的数据：保留不在范围内的数据
                in_range = (
                    pl.col(date_col)
                    >= pl.lit(start_date).str.strptime(pl.Date, "%Y-%m-%d")
                ) & (
                    pl.col(date_col)
                    <= pl.lit(end_date).str.strptime(pl.Date, "%Y-%m-%d")
                )
                keep_mask = keep_mask & ~in_range
            elif start_date:
                # 只删除 start_date 之后的数据
                keep_mask = keep_mask & ~(
                    pl.col(date_col)
                    >= pl.lit(start_date).str.strptime(pl.Date, "%Y-%m-%d")
                )
            elif end_date:
                # 只删除 end_date 之前的数据
                keep_mask = keep_mask & ~(
                    pl.col(date_col)
                    <= pl.lit(end_date).str.strptime(pl.Date, "%Y-%m-%d")
                )

            # 应用过滤条件（保留不符合删除条件的数据）
            df = df.filter(keep_mask)

            # 计算删除的行数
            deleted_count = original_count - len(df)
            total_deleted += deleted_count

            # 写回文件
            if len(df) > 0:
                atomic_write(df, path)
            else:
                # 如果文件为空，删除文件
                path.unlink()

        return total_deleted

    # ============ Metadata operations ============

    def get_years(self, dataset: str) -> list[int]:
        """
        Get available years for a dataset.

        Args:
            dataset: 数据集名称.

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
            dataset: 数据集名称.
            partition_key: 分区键（如年份 "2024"）.

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
            dataset: 数据集名称.
            partition_key: 分区键（如年份 "2024"）.

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
            dataset: 数据集名称.
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
            dataset: 数据集名称.

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
            dataset: 数据集名称.

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
