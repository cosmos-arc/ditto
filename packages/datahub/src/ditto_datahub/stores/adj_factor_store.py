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

from ditto_datahub.stores.parquet_store_base import ParquetStoreBase
from ditto_datahub.types import OnDuplicate


class AdjFactorStore(ParquetStoreBase):
    """
    Adjustment factor data storage with year partitioning.

    Storage structure:
        data_root/
            adj_factor/
                2020.parquet
                2021.parquet
                ...
    """

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
        on_duplicate: OnDuplicate = OnDuplicate.ERROR,
    ) -> tuple[str, str]:
        """
        Write year partition file.

        Strategy: Read existing data → Merge deduplicate → Atomic write.

        Args:
            dataset: Dataset name.
            df: Data to write.
            year: Year partition.
            on_duplicate: 处理重复数据的策略。

        Returns:
            Tuple of (file_path, checksum).

        """
        with span("data.write", dataset=dataset, year=year) as s:
            return self._write_impl(dataset, df, year, on_duplicate, s)

    def _write_impl(
        self,
        dataset: str,
        df: pl.DataFrame,
        year: int,
        on_duplicate: OnDuplicate,
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

            # Check for duplicates
            new_keys = df[["sid", "trade_date"]]
            existing_keys = existing[["sid", "trade_date"]]
            duplicates = new_keys.join(
                existing_keys, on=["sid", "trade_date"], how="inner"
            )

            if len(duplicates) > 0 and on_duplicate == OnDuplicate.ERROR:
                raise ValueError(
                    f"检测到重复数据: {len(duplicates)} 条记录已存在."
                    f"如需覆盖, 请使用 on_duplicate=OnDuplicate.KEEP_LAST"
                )

            if on_duplicate == OnDuplicate.KEEP_FIRST:
                # 保留现有数据，忽略新数据中的重复
                combined = pl.concat([existing, df]).unique(
                    subset=["sid", "trade_date"],
                    keep="first",
                )
            else:  # KEEP_LAST or default
                # 新数据覆盖现有数据
                combined = pl.concat([existing, df]).unique(
                    subset=["sid", "trade_date"],
                    keep="last",
                )
        else:
            combined = df

        # Normalize trade_date to Date type if needed
        if "trade_date" in combined.columns:
            if combined["trade_date"].dtype == pl.String:
                combined = combined.with_columns(
                    pl.col("trade_date").str.strptime(pl.Date, "%Y-%m-%d")
                )
            elif combined["trade_date"].dtype != pl.Date:
                combined = combined.with_columns(pl.col("trade_date").cast(pl.Date))

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
