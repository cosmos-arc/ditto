"""LimitList parquet reader."""

from ditto_data.storage.base.dataset_reader import ParquetDatasetReader
from ditto_platform.foundation import ParquetStore


class LimitListReader(ParquetDatasetReader):
    """Read market/stock/limit_list facts."""

    def __init__(self, store: ParquetStore) -> None:
        super().__init__(store, "market/stock/limit_list")
