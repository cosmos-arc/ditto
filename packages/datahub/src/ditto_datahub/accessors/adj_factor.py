"""AdjFactor Repository for adjustment factor data access."""

from __future__ import annotations

import polars as pl
from ditto_foundation import M, logger, traced
from ditto_foundation.concurrency import FileLockManager

from ditto_datahub.models import OnDuplicate, WriteResult
from ditto_datahub.stores.adj_factor_store import AdjFactorStore


class AdjFactorAccessor:
    """
    Adjustment factor repository for dividend/split/bonus factors.

    Provides domain-level interface for adj_factor data operations,
    coordinating AdjFactorStore with file locking for concurrent safety.
    """

    def __init__(
        self,
        adj_factor_store: AdjFactorStore,
        file_lock: FileLockManager,
    ) -> None:
        """
        Initialize AdjFactorAccessor.

        Args:
            adj_factor_store: Adjustment factor store.
            file_lock: File lock manager for concurrent writes.

        """
        self._adj_factor_store = adj_factor_store
        self._file_lock = file_lock

    @traced("repository.adj_factor.write")
    def write(
        self,
        dataset: str,
        df: pl.DataFrame,
        year: int,
        on_duplicate: OnDuplicate = OnDuplicate.ERROR,
    ) -> WriteResult:
        """
        Write adjustment factor data with file lock protection.

        Args:
            dataset: Dataset name ("adj_factor" or "fund_adj").
            df: Adjustment factor data DataFrame.
            year: Year partition for storage.
            on_duplicate: Strategy for handling duplicate data.

        Returns:
            WriteResult with file_path, checksum, and row counts.

        """
        logger.info(
            "Writing adj_factor data",
            event="adj_factor_write_start",
            dataset=dataset,
            year=year,
            row_count=len(df),
        )

        # Use file lock for concurrent safety
        lock_name = f"adj_factor_write_{dataset}_{year}"
        with self._file_lock.acquire(lock_name, timeout=60.0):
            # Write data
            result = self._adj_factor_store.write(
                dataset, df, year, on_duplicate=on_duplicate
            )
            file_path, checksum = result.file_path, result.checksum

            logger.info(
                "AdjFactor data written",
                event="adj_factor_write_complete",
                dataset=dataset,
                year=year,
                file_path=file_path,
                checksum=checksum,
                rows_written=len(df),
            )

            # Record metrics
            M.data_records.add(len(df), {"dataset": dataset, "operation": "write"})

            return WriteResult(
                file_path=file_path,
                checksum=checksum,
                rows_written=len(df),
                rows_total=len(df),
                blocked=False,
                dq_result=None,
            )
