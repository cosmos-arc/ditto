"""StockLimit parquet reader."""

from ditto_data.storage.base.dataset_reader import ParquetDatasetReader
from ditto_platform.foundation import ParquetStore


class StockLimitReader(ParquetDatasetReader):
    """Read market/stock/limit facts (up/down limit prices, CNY)."""

    def __init__(self, store: ParquetStore) -> None:
        super().__init__(store, "market/stock/limit")
