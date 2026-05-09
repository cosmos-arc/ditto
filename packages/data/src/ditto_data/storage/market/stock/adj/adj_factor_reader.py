"""Stock adjustment factor reader."""

from ditto_data.storage.base.dataset_reader import ParquetDatasetReader
from ditto_platform.foundation import ParquetStore


class StockAdjFactorReader(ParquetDatasetReader):
    """Reader for stock adjustment factor data."""

    def __init__(self, store: ParquetStore) -> None:
        super().__init__(store, "market/stock/adj")
