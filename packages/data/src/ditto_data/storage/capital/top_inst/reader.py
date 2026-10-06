"""TopInst parquet reader."""

from ditto_platform.foundation import ParquetStore

from ditto_data.storage.base.dataset_reader import ParquetDatasetReader


class TopInstReader(ParquetDatasetReader):
    """Read capital/top_inst facts."""

    def __init__(self, store: ParquetStore) -> None:
        super().__init__(store, "capital/top_inst")
