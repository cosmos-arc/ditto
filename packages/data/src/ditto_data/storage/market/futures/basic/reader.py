"""FuturesBasic parquet reader."""

from ditto_data.storage.base.dataset_reader import ParquetDatasetReader
from ditto_platform.foundation import ParquetStore


class FuturesBasicReader(ParquetDatasetReader):
    """Read market/futures/basic facts."""

    def __init__(self, store: ParquetStore) -> None:
        super().__init__(store, "market/futures/basic")
