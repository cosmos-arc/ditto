"""ETF adjustment factor reader."""

from ditto_data.storage.base import ParquetStore
from ditto_data.storage.base.dataset_reader import ParquetDatasetReader


class EtfAdjFactorReader(ParquetDatasetReader):
    """Reader for ETF adjustment factor data."""

    def __init__(self, store: ParquetStore) -> None:
        super().__init__(store, "market/etf/adj")
