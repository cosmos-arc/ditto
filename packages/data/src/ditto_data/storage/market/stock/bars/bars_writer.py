"""Stock daily bars writer."""

from ditto_data.storage.base.dataset_writer import ParquetDatasetWriter
from ditto_platform.foundation.storage import ParquetStore


class StockBarsWriter(ParquetDatasetWriter):
    """Writer for stock daily bars data."""

    def __init__(self, store: ParquetStore) -> None:
        super().__init__(store, "market/stock/bars")
