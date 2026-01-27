"""ParquetStore implementation for year-partitioned Parquet data storage."""

from __future__ import annotations

from pathlib import Path

import polars as pl
from ditto_foundation import logger, traced
from ditto_foundation.util.io import atomic_write, file_md5

from ditto_datahub.models import OnDuplicate
from ditto_datahub.models.storage import WriteResultStore
from ditto_datahub.stores.base.base_store import BaseStore
from ditto_datahub.stores.base.partition_strategy import (
    PartitionStrategy,
    YearlyPartition,
)


class ParquetStore(BaseStore):
    """
    Parquet 文件存储实现.

    按年分区存储数据：data_root/dataset/YYYY.parquet

    支持特性：
    - 按年分区存储
    - 日期范围查询
    - 重复数据处理（error/keep_first/keep_last）
    - 自动去重（batch 内部重复）

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
        super().__init__(data_root)
        self._partition = partition_strategy

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

    # ============ Read operation ============

    @traced("data.read")
    def read(
        self,
        dataset: str,
        sids: list[int] | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        **kwargs: object,
    ) -> pl.DataFrame:
        """
        读取数据.

        Args:
            dataset: 数据集名称.
            sids: 证券 ID 列表（可选）.
            start_date: 起始日期 (YYYY-MM-DD)（可选）.
            end_date: 结束日期 (YYYY-MM-DD)（可选）.
            **kwargs: 其他参数（忽略）.

        Returns:
            DataFrame 包含匹配的记录.

        """
        # 收集所有相关分区文件
        paths = self._collect_paths(dataset, start_date, end_date)

        if not paths:
            return pl.DataFrame()

        # 使用 scan_parquet 实现谓词下推
        lf = pl.scan_parquet(paths)

        # 应用过滤条件
        if sids:
            lf = lf.filter(pl.col("sid").is_in(sids))

        if start_date:
            lf = lf.filter(
                pl.col("trade_date")
                >= pl.lit(start_date).str.strptime(pl.Date, "%Y-%m-%d")
            )

        if end_date:
            lf = lf.filter(
                pl.col("trade_date")
                <= pl.lit(end_date).str.strptime(pl.Date, "%Y-%m-%d")
            )

        # 执行查询
        return lf.collect()

    # ============ Write operation ============

    @traced("data.write")
    def write(
        self,
        dataset: str,
        data: object,
        on_duplicate: str = "error",
        **kwargs: object,
    ) -> WriteResultStore:
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
            return WriteResultStore(
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

        file_path = self._get_path(dataset, str(year))
        is_merge = file_path.exists()

        # 解析去重策略
        strategy = OnDuplicate(on_duplicate)

        # 统计信息
        added = 0
        updated = 0

        # 处理数据
        if is_merge:
            # 合并路径：先对新批次进行去重，保持与非合并路径一致
            df = df.unique(subset=["sid", "trade_date"], keep="first")
            # 读取现有数据
            existing = pl.read_parquet(file_path)
            # 合并数据并获取统计信息
            df, added, updated = self._merge_data(df, existing, strategy)
        else:
            # 新文件，只需去重 batch 内部重复
            df = df.unique(subset=["sid", "trade_date"], keep="first")
            added = len(df)
            updated = 0

        # 准备写入（归一化日期列并排序）
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
            is_merge=is_merge,
            file_path=str(file_path),
            checksum=checksum,
        )

        return WriteResultStore(
            file_path=str(file_path),
            checksum=checksum,
            added=added,
            updated=updated,
            skipped=0,
            is_merge=is_merge,
        )

    def _merge_data(
        self,
        new_df: pl.DataFrame,
        existing_df: pl.DataFrame,
        on_duplicate: OnDuplicate,
    ) -> tuple[pl.DataFrame, int, int]:
        """
        合并新数据与现有数据.

        Args:
            new_df: 新数据.
            existing_df: 现有数据.
            on_duplicate: 重复数据处理策略.

        Returns:
            (合并后的 DataFrame, 新增行数, 更新行数).

        Raises:
            ValueError: 如果 on_duplicate=ERROR 且存在重复数据.

        """
        key_columns = ["sid", "trade_date"]

        # 检测重复数据
        existing_keys = existing_df.select(key_columns)
        new_keys = new_df.select(key_columns)

        # 找出重叠的键
        merged_keys = existing_keys.join(new_keys, on=key_columns, how="inner")
        overlap_count = len(merged_keys)

        added = 0
        updated = 0

        if not merged_keys.is_empty():
            # 存在重复数据
            if on_duplicate == OnDuplicate.ERROR:
                msg = (
                    f"Duplicate data: {overlap_count} overlapping key pairs. "
                    "Use on_duplicate='keep_first' to preserve, or "
                    "on_duplicate='keep_last' to overwrite."
                )
                raise ValueError(msg)
            elif on_duplicate == OnDuplicate.KEEP_FIRST:
                # 保留现有数据，过滤掉新数据中的重复部分
                # 注意：new_df 在调用 _merge_data 前已去重（在 write 方法中）
                new_keys = new_df.select(key_columns)
                # 过滤掉与现有数据重叠的部分
                non_overlapping = new_keys.join(
                    existing_keys, on=key_columns, how="anti"
                )
                new_df = new_df.join(non_overlapping, on=key_columns, how="inner")
                combined = pl.concat([existing_df, new_df])
                added = len(new_df)
                updated = 0
            elif on_duplicate == OnDuplicate.KEEP_LAST:
                # Last-Write-Wins: 新数据覆盖现有数据
                combined = pl.concat([existing_df, new_df])
                combined = combined.unique(subset=key_columns, keep="last")
                # 新增 = 新数据中去重后的行数
                # 更新 = 重叠的行数
                added = len(new_df) - overlap_count
                updated = overlap_count
            else:
                msg = f"Unknown OnDuplicate strategy: {on_duplicate}"
                raise ValueError(msg)
        else:
            # 无重复，直接合并
            combined = pl.concat([existing_df, new_df])
            added = len(new_df)
            updated = 0

        return combined, added, updated

    def _prepare_for_write(self, df: pl.DataFrame) -> pl.DataFrame:
        """
        准备写入：归一化日期列并排序.

        Args:
            df: 输入 DataFrame.

        Returns:
            准备好的 DataFrame.

        """
        # 归一化日期列
        if "trade_date" in df.columns:
            if df["trade_date"].dtype == pl.String:
                df = df.with_columns(
                    pl.col("trade_date").str.strptime(pl.Date, "%Y-%m-%d")
                )
            elif df["trade_date"].dtype != pl.Date:
                df = df.with_columns(pl.col("trade_date").cast(pl.Date))

        # 排序
        return df.sort(["sid", "trade_date"])

    # ============ Delete operation ============

    @traced("data.delete")
    def delete(
        self,
        dataset: str,
        sids: list[int] | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        **kwargs: object,
    ) -> int:
        """
        删除数据.

        Args:
            dataset: 数据集名称.
            sids: 证券 ID 列表（可选）.
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

        for path in paths:
            # 读取现有数据
            df = pl.read_parquet(path)

            # 计算删除前的行数
            original_count = len(df)

            # 构建删除条件：保留不在删除范围内的数据
            keep_mask = pl.lit(True)

            if sids:
                # 删除指定 sid：保留不在 sids 中的数据
                keep_mask = keep_mask & ~pl.col("sid").is_in(sids)

            if start_date and end_date:
                # 删除日期范围内的数据：保留不在范围内的数据
                in_range = (
                    pl.col("trade_date")
                    >= pl.lit(start_date).str.strptime(pl.Date, "%Y-%m-%d")
                ) & (
                    pl.col("trade_date")
                    <= pl.lit(end_date).str.strptime(pl.Date, "%Y-%m-%d")
                )
                keep_mask = keep_mask & ~in_range
            elif start_date:
                # 只删除 start_date 之后的数据
                keep_mask = keep_mask & ~(
                    pl.col("trade_date")
                    >= pl.lit(start_date).str.strptime(pl.Date, "%Y-%m-%d")
                )
            elif end_date:
                # 只删除 end_date 之前的数据
                keep_mask = keep_mask & ~(
                    pl.col("trade_date")
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
