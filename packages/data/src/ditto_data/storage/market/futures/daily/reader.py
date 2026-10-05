"""FuturesDaily parquet reader."""

from ditto_data.storage.base.dataset_reader import ParquetDatasetReader
from ditto_platform.foundation import ParquetStore


class FuturesDailyReader(ParquetDatasetReader):
    """Read market/futures/daily facts."""

    def __init__(self, store: ParquetStore) -> None:
        super().__init__(store, "market/futures/daily")
