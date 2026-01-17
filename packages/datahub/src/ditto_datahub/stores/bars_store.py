"""
Market bars storage with year partitioning.

Stores market daily data (stock/ETF) in Parquet files with year partitioning.
Following design document at docs/design/02_data_design.md.
"""

from __future__ import annotations

import time
from datetime import datetime

import polars as pl
from ditto_foundation import M, logger, traced

from ditto_datahub.stores.parquet_store_base import ParquetStoreBase

# Default year range for date filters
DEFAULT_START_YEAR = 1990
DEFAULT_END_YEAR = 2099


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

    def _get_key_columns(self) -> list[str]:
        """返回键列名."""
        return ["sid", "trade_date"]

    def _get_sort_columns(self) -> list[str]:
        """返回排序列名（BarsStore 使用 trade_date, sid 顺序）."""
        return ["trade_date", "sid"]

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

    def _prepare_for_write(self, df: pl.DataFrame) -> pl.DataFrame:
        """
        准备写入：归一化日期列并排序。

        BarsStore 覆盖此方法以使用特殊的日期列处理和排序顺序。

        Args:
            df: 输入 DataFrame。

        Returns:
            准备好的 DataFrame。

        """
        # Ensure trade_date is date type for sorting
        df = self._ensure_date_column(df)
        # Sort for optimal read performance
        return df.sort(self._get_sort_columns())

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
        start_year = int(start_date[:4]) if start_date else DEFAULT_START_YEAR
        end_year = int(end_date[:4]) if end_date else DEFAULT_END_YEAR

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
