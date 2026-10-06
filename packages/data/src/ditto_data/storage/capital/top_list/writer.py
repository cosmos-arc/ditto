"""TopList parquet writer."""

from ditto_platform.foundation import ParquetStore

from ditto_data.storage.base.dataset_writer import ParquetDatasetWriter


class TopListWriter(ParquetDatasetWriter):
    """Write capital/top_list facts."""

    def __init__(self, store: ParquetStore) -> None:
        super().__init__(store, "capital/top_list")
