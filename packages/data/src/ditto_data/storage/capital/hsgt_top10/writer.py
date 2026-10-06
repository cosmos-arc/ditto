"""HsgtTop10 parquet writer."""

from ditto_platform.foundation import ParquetStore

from ditto_data.storage.base.dataset_writer import ParquetDatasetWriter


class HsgtTop10Writer(ParquetDatasetWriter):
    """Write capital/hsgt_top10 facts."""

    def __init__(self, store: ParquetStore) -> None:
        super().__init__(store, "capital/hsgt_top10")
