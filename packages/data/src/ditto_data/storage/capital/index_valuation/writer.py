"""IndexValuation parquet writer."""

from ditto_platform.foundation import ParquetStore

from ditto_data.storage.base.dataset_writer import ParquetDatasetWriter


class IndexValuationWriter(ParquetDatasetWriter):
    """Write capital/index_valuation facts."""

    def __init__(self, store: ParquetStore) -> None:
        super().__init__(store, "capital/index_valuation")
