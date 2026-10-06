"""HkHold parquet reader."""

from ditto_platform.foundation import ParquetStore

from ditto_data.storage.base.dataset_reader import ParquetDatasetReader


class HkHoldReader(ParquetDatasetReader):
    """Read capital/hk_hold facts."""

    def __init__(self, store: ParquetStore) -> None:
        super().__init__(store, "capital/hk_hold")
