"""
FactorWriter for CQRS pattern.

Provides write access to factor data with PIT support.
Following design document at docs/plans/2026-02-09-datahub-cqrs-refactor.md
"""

from __future__ import annotations

from pathlib import Path

import polars as pl
from ditto_foundation import logger, traced

from ditto_datahub.models import OnDuplicate
from ditto_datahub.models.storage import WriteStoreResult as WriteResult
from ditto_datahub.stores.base import MergeResult, ParquetStore, YearlyPartition


class _FactorParquetWriter(ParquetStore):
    """
    Custom ParquetStore for factor data with PIT support.

    Overrides hook methods to handle PIT-specific logic.
    """

    def _get_key_columns(self) -> list[str]:
        """
        Return key column names for deduplication.

        For PIT data, the key includes effective_from to allow
        multiple versions of the same factor value.
        """
        return ["instrument_id", "trade_date", "factor_id", "effective_from"]

    def _get_sort_columns(self) -> list[str]:
        """Return sort columns."""
        return ["instrument_id", "trade_date", "factor_id", "effective_from"]

    def _get_date_column(self) -> str:
        """Return the date column name (default trade_date)."""
        return "trade_date"

    def _prepare_for_write(self, df: pl.DataFrame) -> pl.DataFrame:
        """
        准备写入：归一化所有日期列并排序。

        Args:
            df: 输入 DataFrame。

        Returns:
            准备好的 DataFrame。

        """
        # 调用父类方法处理 trade_date
        df = super()._prepare_for_write(df)

        # 处理 effective_from 和 effective_to 列
        for col in ["effective_from", "effective_to"]:
            if col in df.columns:
                if df[col].dtype == pl.String:
                    df = df.with_columns(
                        pl.col(col)
                        .str.strptime(pl.Date, "%Y-%m-%d")
                        .fill_null(pl.lit(None, dtype=pl.Date))
                    )
                elif df[col].dtype != pl.Date:
                    df = df.with_columns(pl.col(col).cast(pl.Date))

        # 按键列排序
        sort_cols = self._get_sort_columns()
        return df.sort(sort_cols)

    def _merge_with_existing(
        self,
        df: pl.DataFrame,
        existing: pl.DataFrame,
        on_duplicate: OnDuplicate,
    ) -> MergeResult:
        """
        合并新数据与现有数据（重写以支持 PIT 日期列）。

        Args:
            df: 新数据（未处理）。
            existing: 现有数据。
            on_duplicate: 重复数据处理策略。

        Returns:
            MergeResult 包含合并后的 DataFrame 和统计信息。

        Raises:
            ValueError: 如果 on_duplicate=ERROR 且存在重复数据。

        """
        key_columns = self._get_key_columns()

        # 临时转换日期列以便 join 操作
        # （只在内存中转换，不影响原始 df）
        df_for_join = df.clone()
        for col in ["trade_date", "effective_from", "effective_to"]:
            if col in df_for_join.columns and df_for_join[col].dtype == pl.String:
                df_for_join = df_for_join.with_columns(
                    pl.col(col).str.strptime(pl.Date, "%Y-%m-%d")
                )

        # 检测重复数据
        existing_keys = existing.select(key_columns)
        new_keys = df_for_join.select(key_columns)

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
                    "Use OnDuplicate.KEEP_FIRST to preserve, or "
                    "OnDuplicate.KEEP_LAST to overwrite."
                )
                raise ValueError(msg)
            elif on_duplicate == OnDuplicate.KEEP_FIRST:
                # 保留现有数据，过滤掉新数据中的重复部分
                non_overlapping = new_keys.join(
                    existing_keys, on=key_columns, how="anti"
                )
                # 使用转换后的数据进行 join，但返回原始数据
                df_to_write = df_for_join.join(
                    non_overlapping, on=key_columns, how="inner"
                )
                combined = pl.concat([existing, df_to_write])
                added = len(df_to_write)
                updated = 0
            elif on_duplicate == OnDuplicate.KEEP_LAST:
                # Last-Write-Wins: 新数据覆盖现有数据
                combined = pl.concat([existing, df_for_join])
                combined = combined.unique(subset=key_columns, keep="last")
                added = len(df_for_join) - overlap_count
                updated = overlap_count
            else:
                msg = f"Unknown OnDuplicate strategy: {on_duplicate}"
                raise ValueError(msg)
        else:
            # 无重复，直接合并
            combined = pl.concat([existing, df_for_join])
            added = len(df_for_join)
            updated = 0

        return MergeResult(df=combined, added=added, updated=updated)


class FactorWriter:
    """
    Factor data writer with year partitioning and PIT support.

    Provides write access to factor values in Parquet files
    organized by year. Includes effective_from/effective_to columns
    for Point-in-Time queries.

    Storage structure:
        data_root/factors/factors_narrow/
            2020.parquet
            2021.parquet
            ...

    Schema:
        instrument_id: Instrument ID
        trade_date: Trading date
        factor_id: Factor identifier (e.g., 'factor_momentum_12m')
        factor_class: Class category (fundamental/technical/macro/statistical)
        factor_family: Investment style family (value/momentum/quality/size/volatility)
        exposure: Factor exposure (standardized value)
        raw_value: Raw factor value (unstandardized)
        effective_from: Date when this version becomes effective
        effective_to: Date when this version stops being effective (NULL = current)

    Attributes:
        _store: Custom ParquetStore for factor data.
        _dataset: Dataset path within data_root.

    """

    def __init__(self, data_root: str | Path) -> None:
        """
        Initialize FactorWriter.

        Args:
            data_root: Root directory for data storage.

        """
        self._store = _FactorParquetWriter(Path(data_root), YearlyPartition())
        self._dataset = "factors/factors_narrow"

    @traced("data.factor_write")
    def write(
        self,
        df: pl.DataFrame,
        year: int,
        on_duplicate: OnDuplicate = OnDuplicate.ERROR,
    ) -> WriteResult:
        """
        Write factor data.

        Args:
            df: DataFrame with columns:
                - instrument_id (int)
                - trade_date (date or str YYYY-MM-DD)
                - factor_id (str)
                - factor_class (str)
                - factor_family (str)
                - exposure (float)
                - raw_value (float, optional)
                - effective_from (date or str YYYY-MM-DD)
                - effective_to (date or str YYYY-MM-DD, optional)
            year: Year partition for writing.
            on_duplicate: How to handle duplicates.

        Returns:
            Write result with statistics.

        Raises:
            ValueError: If required columns are missing.

        """
        logger.info(
            "Starting factor data write",
            record_count=len(df),
            year=year,
        )

        # Validate required columns
        required = [
            "instrument_id",
            "trade_date",
            "factor_id",
            "factor_class",
            "factor_family",
            "exposure",
            "effective_from",
        ]
        missing = [col for col in required if col not in df.columns]
        if missing:
            msg = f"Missing required columns: {missing}"
            raise ValueError(msg)

        # Use custom ParquetStore write implementation
        result = self._store.write(self._dataset, df, on_duplicate.value, year=year)

        logger.info(
            "Factor data written successfully",
            record_count=len(df),
            year=year,
            added=result.added,
            updated=result.updated,
        )

        return result

    def delete_partition(self, partition_key: str) -> bool:
        """
        Delete a partition by key.

        Args:
            partition_key: Partition key (e.g., "2024").

        Returns:
            True if deleted, False if file didn't exist.

        """
        return self._store.delete_partition(self._dataset, partition_key)

    @property
    def data_root(self) -> Path:
        """Get the data root directory."""
        return self._store.data_root
