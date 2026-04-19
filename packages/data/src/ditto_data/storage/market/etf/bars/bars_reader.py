"""ETF daily bars reader."""

from ditto_data.storage.base import ParquetStore
from ditto_data.storage.base.dataset_reader import ParquetDatasetReader


class EtfBarsReader(ParquetDatasetReader):
    """Reader for ETF daily bars data."""

    def __init__(self, store: ParquetStore) -> None:
        super().__init__(store, "market/etf/bars")
