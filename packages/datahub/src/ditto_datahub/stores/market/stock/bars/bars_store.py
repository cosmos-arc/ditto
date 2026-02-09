from __future__ import annotations

from pathlib import Path

import polars as pl
from ditto_datahub.models import OnDuplicate
from ditto_datahub.models.storage import WriteStoreResult
from ditto_datahub.stores.market.stock.bars.bars_reader import StockBarsReader
from ditto_datahub.stores.market.stock.bars.bars_writer import StockBarsWriter

"""Stock daily bars storage with year partitioning.

This is a compatibility layer that combines StockBarsReader and StockBarsWriter.
Following design document at docs/design/02_data_design.md.

This class will be deprecated in favor of using StockBarsReader and StockBarsWriter
directly in CQRS pattern.
"""


class StockBarsStore:
    """
    Stock daily bars data storage with year partitioning.

    This is a compatibility layer that combines StockBarsReader and StockBarsWriter.
    Direct use of StockBarsReader and StockBarsWriter is recommended for new code.

    Storage structure:
        data_root/
            market/stock/bars/
                2020.parquet
                2021.parquet
                ...

    """

    def __init__(self, data_root: Path) -> None:
        """
        Initialize StockBarsStore.

        Args:
            data_root: Root directory for data storage.

        """
        self._reader = StockBarsReader(data_root)
        self._writer = StockBarsWriter(data_root)

    # ============ Read operations (delegated to Reader) ============

    def read(
        self,
        instrument_ids: list[int] | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        """Read bars data from the store."""
        return self._reader.read(
            instrument_ids=instrument_ids,
            start_date=start_date,
            end_date=end_date,
        )

    def count(
        self,
        instrument_ids: list[int] | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> int:
        """Count records in the dataset."""
        return self._reader.count(
            instrument_ids=instrument_ids,
            start_date=start_date,
            end_date=end_date,
        )

    # ============ Write operations (delegated to Writer) ============

    def write(
        self,
        df: pl.DataFrame,
        year: int,
        on_duplicate: OnDuplicate = OnDuplicate.ERROR,
    ) -> WriteStoreResult:
        """Write bars data to the store."""
        return self._writer.write(df, year, on_duplicate)

    def delete(
        self,
        instrument_ids: list[int] | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> int:
        """Delete bars data from the store."""
        return self._writer.delete(
            instrument_ids=instrument_ids,
            start_date=start_date,
            end_date=end_date,
        )

    def delete_partition(self, partition_key: str) -> bool:
        """Delete a partition by key."""
        return self._writer.delete_partition(partition_key)

    # ============ Metadata operations (delegated to Reader) ============

    def get_years(self) -> list[int]:
        """Get available years for this dataset."""
        return self._reader.get_years()

    def get_date_range(self) -> tuple[str | None, str | None]:
        """Get overall date range for the dataset."""
        return self._reader.get_date_range()

    def list_instrument_ids(self) -> list[int]:
        """List unique instrument IDs in the dataset."""
        return self._reader.list_instrument_ids()

    @property
    def data_root(self) -> Path:
        """Get the data root directory."""
        return self._reader.data_root
