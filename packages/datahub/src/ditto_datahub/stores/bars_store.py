"""
Market bars storage with year partitioning.

Stores market daily data (stock/ETF) in Parquet files with year partitioning.
Following design document at docs/design/02_data_design.md.
"""

from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path
from typing import Any

import polars as pl
from ditto_foundation import M, logger, span, traced
from ditto_foundation.util.io import atomic_write, file_md5

from ditto_datahub.stores.parquet_store_base import ParquetStoreBase
from ditto_datahub.types import OnDuplicate


class BarsStore(ParquetStoreBase):
    """
    Market bars data storage with year partitioning.

    Storage structure:
        data_root/
            stock_daily/
                2020.parquet
                2021.parquet
                ...
            etf_daily/
                2020.parquet
                ...
    """

    def _ensure_date_column(self, df: pl.DataFrame) -> pl.DataFrame:
        """
        Ensure trade_date column is Date type for sorting.

        Args:
            df: Input DataFrame.

        Returns:
            DataFrame with trade_date as Date type.

        """
        dtype = df["trade_date"].dtype

        # If already Date type, return as-is
        if dtype == pl.Date:
            return df

        # If String type, convert to Date
        if dtype == pl.String:
            return df.with_columns(pl.col("trade_date").str.to_date())

        # If Object type (could be date objects or strings), try to convert
        if dtype == pl.Object:
            # Try casting to string first, then to date
            try:
                return df.with_columns(
                    pl.col("trade_date").cast(pl.String).str.to_date()
                )
            except Exception:
                # If that fails, the column might already contain date objects
                # Just return the DataFrame as-is and hope for the best
                return df

        return df

    def _ensure_dataset_dir(self, dataset: str) -> Path:
        """
        Ensure dataset directory exists.

        Args:
            dataset: Dataset name.

        Returns:
            Path to the dataset directory.

        """
        dataset_dir = self._data_root / dataset
        dataset_dir.mkdir(parents=True, exist_ok=True)
        return dataset_dir

    def _merge_with_existing(
        self,
        df: pl.DataFrame,
        file_path: Path,
        on_duplicate: OnDuplicate,
    ) -> pl.DataFrame:
        """
        Merge DataFrame with existing data if file exists.

        Args:
            df: New data to write.
            file_path: Path to existing data file.
            on_duplicate: 策略处理重复数据.

        Returns:
            Merged DataFrame with unique sid/date pairs.

        Raises:
            ValueError: 如果 on_duplicate=ERROR 且存在重复数据.

        """
        if file_path.exists():
            existing = pl.read_parquet(file_path)

            # 检测重复数据
            existing_keys = existing.select(["sid", "trade_date"])
            new_keys = df.select(["sid", "trade_date"])

            # 找出重叠的 (sid, trade_date) 对
            merged_keys = existing_keys.join(
                new_keys, on=["sid", "trade_date"], how="inner"
            )

            if not merged_keys.is_empty():
                # 存在重复数据
                if on_duplicate == OnDuplicate.ERROR:
                    dup_count = len(merged_keys)
                    msg = (
                        "Duplicate data: "
                        f"{dup_count} overlapping (sid, trade_date) pairs. "
                        "Use OnDuplicate.KEEP_FIRST to preserve, or "
                        "OnDuplicate.KEEP_LAST to overwrite."
                    )
                    raise ValueError(msg)
                elif on_duplicate == OnDuplicate.KEEP_FIRST:
                    # 保留现有数据，过滤掉新数据中的重复部分
                    # 使用 anti join 获取新数据中不重复的部分
                    non_overlapping = new_keys.join(
                        existing_keys, on=["sid", "trade_date"], how="anti"
                    )
                    # 过滤 df 以保留不重复的行
                    df = df.join(non_overlapping, on=["sid", "trade_date"], how="inner")
                    combined = pl.concat([existing, df])
                elif on_duplicate == OnDuplicate.KEEP_LAST:
                    # Last-Write-Wins: 新数据覆盖现有数据
                    combined = pl.concat([existing, df])
                    combined = combined.unique(
                        subset=["sid", "trade_date"],
                        keep="last",
                    )
                else:
                    raise ValueError(f"Unknown OnDuplicate strategy: {on_duplicate}")
            else:
                # 无重复，直接合并
                combined = pl.concat([existing, df])
        else:
            combined = df
        return combined

    def _prepare_for_write(self, df: pl.DataFrame) -> pl.DataFrame:
        """
        Prepare DataFrame for writing: normalize dates and sort.

        Args:
            df: Input DataFrame.

        Returns:
            Prepared DataFrame with Date type and sorted.

        """
        # Ensure trade_date is date type for sorting
        df = self._ensure_date_column(df)
        # Sort for optimal read performance
        return df.sort(["trade_date", "sid"])

    # ============ Read operations ============

    def _build_filter_conditions(
        self,
        lf: pl.LazyFrame,
        sids: list[int] | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.LazyFrame:
        """
        Build filter conditions for LazyFrame.

        Args:
            lf: LazyFrame to filter.
            sids: Filter by security IDs.
            start_date: Start date (YYYY-MM-DD).
            end_date: End date (YYYY-MM-DD).

        Returns:
            Filtered LazyFrame.

        """
        if sids:
            lf = lf.filter(pl.col("sid").is_in(sids))

        if start_date:
            start_dt = datetime.strptime(start_date, "%Y-%m-%d").date()
            lf = lf.filter(pl.col("trade_date") >= pl.lit(start_dt))

        if end_date:
            end_dt = datetime.strptime(end_date, "%Y-%m-%d").date()
            lf = lf.filter(pl.col("trade_date") <= pl.lit(end_dt))

        return lf

    @traced("data.read")
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
            dataset: Dataset name (e.g., "stock_daily", "etf_daily").
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

        # Scan and apply filters
        lf = pl.scan_parquet([str(p) for p in paths])
        lf = self._build_filter_conditions(lf, sids, start_date, end_date)
        result = lf.unique(subset=["sid", "trade_date"], keep="last").collect()

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
        on_duplicate: OnDuplicate = OnDuplicate.ERROR,
    ) -> tuple[str, str]:
        """
        Write year partition file.

        Strategy: Read existing data → Merge deduplicate → Atomic write.

        Args:
            dataset: Dataset name.
            df: Data to write.
            year: Year partition.
            on_duplicate: 策略处理重复数据 (默认 ERROR 报错).

        Returns:
            Tuple of (file_path, checksum).

        """
        with span("data.write", dataset=dataset, year=year) as s:
            return self._write_impl(dataset, df, year, s, on_duplicate)

    def _write_impl(
        self,
        dataset: str,
        df: pl.DataFrame,
        year: int,
        span_ctx: Any,
        on_duplicate: OnDuplicate,
    ) -> tuple[str, str]:
        start_time = time.time()

        # Ensure dataset directory exists
        self._ensure_dataset_dir(dataset)

        file_path = self._get_path(dataset, year)
        is_merge = file_path.exists()

        # Merge with existing data and prepare for write
        combined = self._merge_with_existing(df, file_path, on_duplicate)
        combined = self._prepare_for_write(combined)

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
