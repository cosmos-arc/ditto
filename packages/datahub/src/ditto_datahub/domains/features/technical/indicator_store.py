"""
IndicatorStore for technical indicator data storage.

技术指标数据存储，使用 Parquet 格式按年份分区存储.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import polars as pl
from ditto_foundation import logger, traced

from ditto_datahub.models import OnDuplicate
from ditto_datahub.models.storage import WriteResultStore as WriteResult
from ditto_datahub.stores.parquet_store_base import ParquetStoreBase


class IndicatorStore(ParquetStoreBase):
    """
    Technical indicator data storage with year partitioning.

    Stores technical indicator values in Parquet files organized by year.
    Follows the narrow table pattern for flexibility.

    Storage structure:
        data_root/features/technical/indicators_narrow/
            2020.parquet
            2021.parquet
            ...

    Schema:
        sid: Security ID
        trade_date: Trading date
        indicator_id: Indicator identifier (e.g., 'indicator_rsi_14')
        indicator_type: Type category (trend/momentum/volatility/volume)
        value: Indicator value
        calc_time: Calculation timestamp
    """

    def __init__(self, data_root: Path) -> None:
        """
        Initialize IndicatorStore.

        Args:
            data_root: Root directory for data storage.

        """
        super().__init__(data_root)

    def _get_dataset(self) -> str:
        """Return dataset name for technical indicators."""
        return "features/technical/indicators_narrow"

    def _get_key_columns(self) -> list[str]:
        """Return key column names for deduplication."""
        return ["sid", "trade_date", "indicator_id"]

    @traced("data.indicator_write")
    def write(
        self,
        df: pl.DataFrame,
        year: int,
        on_duplicate: OnDuplicate = OnDuplicate.ERROR,
    ) -> WriteResult:
        """
        Write technical indicator data.

        Args:
            df: DataFrame with columns:
                - sid (int)
                - trade_date (date or str YYYY-MM-DD)
                - indicator_id (str)
                - indicator_type (str)
                - value (float)
                - calc_time (str or datetime)
            year: Year partition for writing.
            on_duplicate: How to handle duplicates.

        Returns:
            Write result with statistics.

        Raises:
            ValueError: If required columns are missing.

        """
        logger.info(
            "Starting technical indicator data write",
            record_count=len(df),
            year=year,
        )

        # Validate required columns
        required = ["sid", "trade_date", "indicator_id", "indicator_type", "value"]
        missing = [col for col in required if col not in df.columns]
        if missing:
            msg = f"Missing required columns: {missing}"
            raise ValueError(msg)

        # Use parent class write implementation
        result = super().write(df, year=year, on_duplicate=on_duplicate)

        logger.info(
            "Technical indicator data written successfully",
            record_count=len(df),
            year=year,
            added=result.added,
            updated=result.updated,
        )

        return result

    @traced("data.indicator_query")
    def read(
        self,
        sids: list[int] | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        indicator_types: list[str] | None = None,
        indicator_ids: list[str] | None = None,
    ) -> pl.DataFrame:
        """
        Query technical indicator data.

        Args:
            sids: Filter by security IDs (None = all).
            start_date: Start date (YYYY-MM-DD).
            end_date: End date (YYYY-MM-DD).
            indicator_types: Filter by indicator types (None = all).
            indicator_ids: Filter by indicator IDs (None = all).

        Returns:
            DataFrame with indicator data.

        """
        logger.debug(
            "Querying technical indicator data",
            sids=sids,
            start_date=start_date,
            end_date=end_date,
            indicator_types=indicator_types,
            indicator_ids=indicator_ids,
        )

        # Determine year range from date filters
        start_year = int(start_date[:4]) if start_date else 1990
        end_year = int(end_date[:4]) if end_date else 2099

        paths = self._collect_paths(start_year, end_year)

        if not paths:
            logger.info(
                "No data found for query",
                event="data_read_complete",
                dataset=self._dataset,
                start_date=start_date,
                end_date=end_date,
                row_count=0,
                duration_ms=0,
            )
            return pl.DataFrame()

        # Scan and filter - NO deduplication on (sid, trade_date)
        # because key is (sid, trade_date, indicator_id)
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

        # Collect without deduplication (same sid/date can have multiple indicators)
        df = lf.sort(["sid", "trade_date", "indicator_id"]).collect()

        # Apply indicator_id filter
        if not df.is_empty() and indicator_ids:
            df = df.filter(pl.col("indicator_id").is_in(indicator_ids))

        # Apply indicator_type filter
        if not df.is_empty() and indicator_types:
            df = df.filter(pl.col("indicator_type").is_in(indicator_types))

        return df

    def _get_sort_columns(self) -> list[str]:
        """Return sort columns."""
        return ["sid", "trade_date", "indicator_id"]
