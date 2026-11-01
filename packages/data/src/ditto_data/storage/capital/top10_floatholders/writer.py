"""Top10 floatholders parquet writer."""

from ditto_platform.foundation import ParquetStore

from ditto_data.storage.base.dataset_writer import ParquetDatasetWriter


class Top10FloatholdersWriter(ParquetDatasetWriter):
    """Write capital/top10_floatholders facts."""

    def __init__(self, store: ParquetStore) -> None:
        super().__init__(store, "capital/top10_floatholders")
