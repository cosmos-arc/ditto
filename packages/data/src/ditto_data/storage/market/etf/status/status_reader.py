"""ETF status reader."""

from ditto_data.storage.base import ParquetStore
from ditto_data.storage.base.dataset_reader import ParquetDatasetReader


class EtfStatusReader(ParquetDatasetReader):
    """Reader for ETF status data."""

    def __init__(self, store: ParquetStore) -> None:
        super().__init__(store, "market/etf/status")
