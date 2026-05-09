"""Index daily bars reader."""

from ditto_platform.foundation import ParquetStore

from ditto_data.storage.base.dataset_reader import ParquetDatasetReader


class IndexBarsReader(ParquetDatasetReader):
    """Reader for index daily bars data."""

    def __init__(self, store: ParquetStore) -> None:
        super().__init__(store, "market/index/bars")
