"""Stock status writer."""

from __future__ import annotations

import polars as pl
from ditto_data.models import OnDuplicate
from ditto_data.models.storage import WriteStoreResult
from ditto_data.storage.base import ParquetStore
from ditto_data.storage.base.dataset_writer import ParquetDatasetWriter


class StockStatusWriter(ParquetDatasetWriter):
    """Writer for stock status data."""

    def __init__(self, store: ParquetStore) -> None:
        super().__init__(store, "market/stock/status")

    def write(
        self,
        df: pl.DataFrame,
        year: int,
        on_duplicate: OnDuplicate = OnDuplicate.KEEP_LAST,
    ) -> WriteStoreResult:
        """Write data with KEEP_LAST default."""
        return super().write(df, year, on_duplicate)
