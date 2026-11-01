"""Top10 holders parquet reader."""

from ditto_platform.foundation import ParquetStore

from ditto_data.storage.base.dataset_reader import ParquetDatasetReader


class Top10HoldersReader(ParquetDatasetReader):
    """Read capital/top10_holders facts."""

    def __init__(self, store: ParquetStore) -> None:
        super().__init__(store, "capital/top10_holders")
