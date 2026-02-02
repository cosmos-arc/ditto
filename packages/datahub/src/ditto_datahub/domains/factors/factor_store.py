"""FactorStore for factor data storage with PIT support."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import polars as pl
from ditto_foundation import logger, traced

from ditto_datahub.models import OnDuplicate
from ditto_datahub.models.storage import WriteResultStore as WriteResult
from ditto_datahub.stores.parquet_store_base import MergeResult, ParquetStoreBase


class FactorStore(ParquetStoreBase):
    """
    Factor data storage with year partitioning and PIT support.

    Stores factor values in Parquet files organized by year.
    Includes effective_from/effective_to columns for Point-in-Time queries.

    Storage structure:
        data_root/factors/factors_narrow/
            2020.parquet
            2021.parquet
            ...

    Schema:
        sid: Security ID
        trade_date: Trading date
        factor_id: Factor identifier (e.g., 'factor_momentum_12m')
        factor_class: Class category (fundamental/technical/macro/statistical)
        factor_family: Investment style family (value/momentum/quality/size/volatility)
        exposure: Factor exposure (standardized value)
        raw_value: Raw factor value (unstandardized)
        effective_from: Date when this version becomes effective
        effective_to: Date when this version stops being effective (NULL = current)
    """

    # Year range defaults (中国股市成立年份 / 遥远的未来年份)
    DEFAULT_START_YEAR = 1990
    DEFAULT_END_YEAR = 2099

    def __init__(self, data_root: Path) -> None:
        """
        Initialize FactorStore.

        Args:
            data_root: Root directory for data storage.

        """
        super().__init__(data_root)
        self._dataset = "factors/factors_narrow"

    def _get_dataset(self) -> str:
        """Return dataset name for factors."""
        return "factors/factors_narrow"

    def _get_key_columns(self) -> list[str]:
        """
        Return key column names for deduplication.

        For PIT data, the key includes effective_from to allow
        multiple versions of the same factor value.
        """
        return ["sid", "trade_date", "factor_id", "effective_from"]

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
                - sid (int)
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
            "sid",
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

        # Use parent class write implementation
        result = super().write(df, year=year, on_duplicate=on_duplicate)

        logger.info(
            "Factor data written successfully",
            record_count=len(df),
            year=year,
            added=result.added,
            updated=result.updated,
        )

        return result

    @traced("data.factor_query")
    def read(
        self,
        sids: list[int] | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        as_of_date: str | None = None,
    ) -> pl.DataFrame:
        """
        Query factor data (PIT-safe).

        Args:
            sids: Filter by security IDs (None = all).
            start_date: Start date (YYYY-MM-DD).
            end_date: End date (YYYY-MM-DD).
            as_of_date: PIT query date - only return data effective as of this date.

        Returns:
            DataFrame with factor data.

        """
        logger.debug(
            "Querying factor data",
            sids=sids,
            start_date=start_date,
            end_date=end_date,
            as_of_date=as_of_date,
        )

        # Determine year range from date filters
        start_year = (
            int(start_date[:4]) if start_date else FactorStore.DEFAULT_START_YEAR
        )
        end_year = int(end_date[:4]) if end_date else FactorStore.DEFAULT_END_YEAR

        paths = self._collect_paths(start_year, end_year)

        if not paths:
            logger.debug(
                "No data files found for query",
                event="data_read_complete",
                dataset=self._dataset,
                start_date=start_date,
                end_date=end_date,
                row_count=0,
            )
            return pl.DataFrame()

        # Scan and filter - NO deduplication (PIT data has multiple versions)
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

        # Collect without deduplication
        df = lf.sort(["sid", "trade_date"]).collect()

        if df.is_empty():
            return pl.DataFrame()

        # Apply PIT filtering if as_of_date is specified
        if as_of_date:
            as_of_dt = datetime.strptime(as_of_date, "%Y-%m-%d").date()
            df = df.filter(
                (pl.col("effective_from") <= pl.lit(as_of_dt))
                & (
                    (pl.col("effective_to").is_null())
                    | (pl.col("effective_to") > pl.lit(as_of_dt))
                )
            )
            # For each (sid, trade_date, factor_id), keep only the latest version
            # (the one with the most recent effective_from)
            df = df.sort(
                ["sid", "trade_date", "factor_id", "effective_from"],
                descending=[False, False, False, True],
            ).unique(
                subset=["sid", "trade_date", "factor_id"],
                keep="first",
            )
            df = df.sort(["sid", "trade_date", "factor_id"])

        return df

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
        file_path: Path,
        on_duplicate: OnDuplicate,
    ) -> MergeResult:
        """
        合并新数据与现有数据（重写以支持 PIT 日期列）。

        Args:
            df: 新数据（未处理）。
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
                    # 使用转换后的数据进行 join，但返回原始数据
                    df_to_write = df_for_join.join(
                        non_overlapping, on=key_columns, how="inner"
                    )
                    combined = pl.concat([existing, df_to_write])
                    # added = 新数据中去重后的行数
                    added = len(df_to_write)
                    updated = 0
                elif on_duplicate == OnDuplicate.KEEP_LAST:
                    # Last-Write-Wins: 新数据覆盖现有数据
                    combined = pl.concat([existing, df_for_join])
                    combined = combined.unique(subset=key_columns, keep="last")
                    # added = 新数据中非重叠的行数
                    added = len(df_for_join) - overlap_count
                    # updated = 重叠的行数
                    updated = overlap_count
                else:
                    raise ValueError(f"Unknown OnDuplicate strategy: {on_duplicate}")
            else:
                # 无重复，直接合并
                combined = pl.concat([existing, df_for_join])
                added = len(df_for_join)
                updated = 0
        else:
            combined = df
            added = len(df)
            updated = 0

        return MergeResult(df=combined, added=added, updated=updated)

    def _get_sort_columns(self) -> list[str]:
        """Return sort columns."""
        return ["sid", "trade_date", "factor_id", "effective_from"]
