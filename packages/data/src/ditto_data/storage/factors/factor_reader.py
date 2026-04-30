"""
FactorReader for CQRS pattern.

Provides read-only access to factor data with PIT support.
Following design document at docs/plans/2026-02-09-data-cqrs-refactor.md
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import polars as pl
from ditto_platform.foundation import logger, traced

from ditto_data.storage.base import ParquetStore, YearlyPartition


class _FactorParquetReader(ParquetStore):
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


class FactorReader:
    """
    Factor data reader with PIT support.

    Provides read-only access to factor values in Parquet files
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
        Initialize FactorReader.

        Args:
            data_root: Root directory for data storage.

        """
        self._store = _FactorParquetReader(Path(data_root), YearlyPartition())
        self._dataset = "factors/factors_narrow"

    @traced("data.factor_query")
    def read(
        self,
        instrument_ids: list[int] | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        as_of_date: str | None = None,
        factor_ids: list[str] | None = None,
    ) -> pl.DataFrame:
        """
        Query factor data (PIT-safe).

        Args:
            instrument_ids: Filter by instrument IDs (None = all).
            start_date: Start date (YYYY-MM-DD).
            end_date: End date (YYYY-MM-DD).
            as_of_date: PIT query date - only return data effective as of this date.
            factor_ids: Filter by factor IDs (None = all).

        Returns:
            DataFrame with factor data.

        """
        logger.debug(
            "Querying factor data",
            instrument_ids=instrument_ids,
            start_date=start_date,
            end_date=end_date,
            as_of_date=as_of_date,
            factor_ids=factor_ids,
        )

        # Use custom ParquetStore to get raw data
        df = self._store.read(
            self._dataset,
            instrument_ids=instrument_ids,
            start_date=start_date,
            end_date=end_date,
        )

        if df.is_empty():
            return pl.DataFrame()

        # Apply factor_id filter
        if factor_ids:
            df = df.filter(pl.col("factor_id").is_in(factor_ids))

        # Apply PIT filtering if as_of_date is specified
        if as_of_date:
            as_of_dt = datetime.strptime(as_of_date, "%Y-%m-%d").date()
            # PIT spec: effective_to 表示"失效日期(不含)"
            # 使用 > 而非 >= : effective_to > as_of_date 表示版本在该日期前有效
            # 详见 .claude/rules/pit.md
            df = df.filter(
                (pl.col("effective_from") <= pl.lit(as_of_dt))
                & (
                    (pl.col("effective_to").is_null())
                    | (pl.col("effective_to") > pl.lit(as_of_dt))
                )
            )
            # Keep only the latest version for each
            # (instrument_id, trade_date, factor_id).
            df = df.sort(
                ["instrument_id", "trade_date", "factor_id", "effective_from"],
                descending=[False, False, False, True],
            ).unique(
                subset=["instrument_id", "trade_date", "factor_id"],
                keep="first",
            )
            df = df.sort(["instrument_id", "trade_date", "factor_id"])

        return df

    # ============ Metadata operations ============

    def get_years(self) -> list[int]:
        """Get available years for this dataset."""
        return self._store.get_years(self._dataset)

    def get_checksum(self, partition_key: str) -> str:
        """
        Get MD5 checksum of a partition.

        Args:
            partition_key: Partition key (e.g., "2024").

        Returns:
            Checksum hex string, or empty string if file doesn't exist.

        """
        return self._store.get_checksum(self._dataset, partition_key)

    def count(
        self,
        instrument_ids: list[int] | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> int:
        """
        Count records in the dataset.

        Args:
            instrument_ids: Filter by instrument IDs.
            start_date: Start date (YYYY-MM-DD).
            end_date: End date (YYYY-MM-DD).

        Returns:
            Number of matching records.

        """
        return self._store.count(
            self._dataset,
            instrument_ids=instrument_ids,
            start_date=start_date,
            end_date=end_date,
        )

    def get_date_range(self) -> tuple[str | None, str | None]:
        """
        Get overall date range for the dataset.

        Returns:
            Tuple of (start_date, end_date) as strings, or (None, None) if empty.

        """
        return self._store.get_date_range(self._dataset)

    def list_instrument_ids(self) -> list[int]:
        """
        List unique instrument IDs in the dataset.

        Returns:
            Sorted list of unique instrument IDs.

        """
        return self._store.list_instrument_ids(self._dataset)
