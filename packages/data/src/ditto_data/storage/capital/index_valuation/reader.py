"""IndexValuation parquet reader."""

from ditto_platform.foundation import ParquetStore

from ditto_data.storage.base.dataset_reader import ParquetDatasetReader


class IndexValuationReader(ParquetDatasetReader):
    """Read capital/index_valuation facts."""

    def __init__(self, store: ParquetStore) -> None:
        super().__init__(store, "capital/index_valuation")
