"""FuturesBasic parquet writer."""

from ditto_data.storage.base.dataset_writer import ParquetDatasetWriter
from ditto_platform.foundation import ParquetStore


class FuturesBasicWriter(ParquetDatasetWriter):
    """Write market/futures/basic facts."""

    def __init__(self, store: ParquetStore) -> None:
        super().__init__(store, "market/futures/basic")
