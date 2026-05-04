"""Stock status reader."""

from ditto_data.storage.base.dataset_reader import ParquetDatasetReader
from ditto_platform.foundation.storage import ParquetStore


class StockStatusReader(ParquetDatasetReader):
    """Reader for stock status data."""

    def __init__(self, store: ParquetStore) -> None:
        super().__init__(store, "market/stock/status")
