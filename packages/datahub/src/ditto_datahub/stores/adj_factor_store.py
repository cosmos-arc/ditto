"""
Adjustment factor storage with year partitioning.

Stores price adjustment factors for dividend/split/bonus events in Parquet files
with year partitioning. Following design document at docs/design/02_data_design.md.
"""

from __future__ import annotations

import time
from datetime import datetime

import polars as pl
from ditto_foundation import M, logger, traced

from ditto_datahub.stores.parquet_store_base import ParquetStoreBase


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

    def _get_key_columns(self) -> list[str]:
        """返回键列名."""
        return ["sid", "trade_date"]

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
