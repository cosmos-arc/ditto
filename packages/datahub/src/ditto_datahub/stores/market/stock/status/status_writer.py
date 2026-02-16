from __future__ import annotations

from pathlib import Path

import polars as pl
from ditto_datahub.models.storage import WriteStoreResult
from ditto_infra.foundation import logger
from ditto_infra.foundation.util.io import atomic_write, file_md5

"""Stock status writer.

Provides write access to stock status data stored in Parquet files
with year partitioning. Following design document at docs/design/02_data_design.md.
"""


class StockStatusWriter:
    """
    Stock status data writer.

    Provides write access to stock status data with year partitioning.
    Strategy: Read existing data → Merge deduplicate → Atomic write.

    Storage structure:
        data_root/
            market/stock/status/
                2020.parquet
                2021.parquet
                ...

    Attributes:
        DATASET: Dataset name for stock status.

    """

    DATASET: str = "market/stock/status"

    def __init__(self, data_root: Path) -> None:
        """
        Initialize StockStatusWriter.

        Args:
            data_root: Root directory for data storage.

        """
        self._data_root = Path(data_root)
        self._dataset = self.DATASET

    def _get_path(self, year: int) -> Path:
        """
        Get year partition file path.

        Args:
            year: Year partition.

        Returns:
            Path to the Parquet file.

        """
        return self._data_root / self._dataset / f"{year}.parquet"

    # ============ Write operations ============

    def write(
        self,
        df: pl.DataFrame,
        year: int,
    ) -> WriteStoreResult:
        """
        Write year partition file.

        Strategy: Read existing data → Merge deduplicate → Atomic write.

        Args:
            df: Data to write.
            year: Year partition.

        Returns:
            Write result statistics.

        """
        dataset_dir = self._data_root / self._dataset
        dataset_dir.mkdir(parents=True, exist_ok=True)

        file_path = self._get_path(year)
        is_merge = file_path.exists()

        # Merge with existing data
        existing_len = 0
        if file_path.exists():
            existing = pl.read_parquet(file_path)
            existing_len = len(existing)
            combined = pl.concat([existing, df]).unique(
                subset=["instrument_id", "trade_date"],
                keep="last",  # New data overwrites
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
        combined = combined.sort(["instrument_id", "trade_date"])

        # Atomic write
        atomic_write(combined, file_path)

        # Calculate checksum
        checksum = file_md5(file_path)

        logger.info(
            "Data write completed",
            event="data_write_complete",
            dataset=self._dataset,
            year=year,
            row_count=len(df),
            total_rows=len(combined),
            is_merge=is_merge,
            file_path=str(file_path),
            checksum=checksum,
        )

        # Calculate added/updated counts
        if is_merge:
            added = max(0, len(combined) - existing_len)
            updated = len(combined) - added
        else:
            added = len(df)
            updated = 0

        return WriteStoreResult(
            file_path=str(file_path),
            checksum=checksum,
            added=added,
            updated=updated,
            skipped=0,
            is_merge=is_merge,
        )

    def delete(
        self,
        instrument_ids: list[int] | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> int:
        """
        Delete status data from the store.

        Args:
            instrument_ids: Filter by instrument IDs.
            start_date: Start date (YYYY-MM-DD).
            end_date: End date (YYYY-MM-DD).

        Returns:
            Number of deleted records.

        """
        # This is a complex operation that would require reading,
        # filtering, and rewriting partitions. For now, return 0.
        # Full implementation would need to handle partition-level deletes.
        logger.warning(
            "Delete operation not fully implemented for StockStatusWriter",
            event="data_delete_not_implemented",
            dataset=self._dataset,
        )
        return 0

    def delete_partition(self, partition_key: str) -> bool:
        """
        Delete a partition by key.

        Args:
            partition_key: Partition key (e.g., "2024").

        Returns:
            True if deleted, False if file didn't exist.

        """
        path = self._data_root / self._dataset / f"{partition_key}.parquet"
        if path.exists():
            path.unlink()
            return True
        return False

    # ============ Metadata operations ============

    def get_checksum(self, year: int) -> str:
        """
        Get MD5 checksum of a year partition.

        Args:
            year: Year partition.

        Returns:
            Checksum hex string, or empty string if file doesn't exist.

        """
        path = self._get_path(year)
        if path.exists():
            return file_md5(path)
        return ""

    @property
    def data_root(self) -> Path:
        """
        Get the data root directory.

        Returns:
            Data root directory path.

        """
        return self._data_root
