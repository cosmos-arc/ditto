"""LimitList parquet writer."""

from ditto_data.storage.base.dataset_writer import ParquetDatasetWriter
from ditto_platform.foundation import ParquetStore


class LimitListWriter(ParquetDatasetWriter):
    """Write market/stock/limit_list facts."""

    def __init__(self, store: ParquetStore) -> None:
        super().__init__(store, "market/stock/limit_list")
