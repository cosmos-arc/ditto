"""Top10 floatholders parquet reader."""

from ditto_platform.foundation import ParquetStore

from ditto_data.storage.base.dataset_reader import ParquetDatasetReader


class Top10FloatholdersReader(ParquetDatasetReader):
    """Read capital/top10_floatholders facts."""

    def __init__(self, store: ParquetStore) -> None:
        super().__init__(store, "capital/top10_floatholders")
