"""StockLimit parquet writer."""

from ditto_data.storage.base.dataset_writer import ParquetDatasetWriter
from ditto_platform.foundation import ParquetStore


class StockLimitWriter(ParquetDatasetWriter):
    """Write market/stock/limit facts (up/down limit prices, CNY)."""

    def __init__(self, store: ParquetStore) -> None:
        super().__init__(store, "market/stock/limit")
