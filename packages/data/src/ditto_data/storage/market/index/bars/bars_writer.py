"""Index daily bars writer."""

from ditto_platform.foundation import ParquetStore

from ditto_data.storage.base.dataset_writer import ParquetDatasetWriter


class IndexBarsWriter(ParquetDatasetWriter):
    """Writer for index daily bars data."""

    def __init__(self, store: ParquetStore) -> None:
        super().__init__(store, "market/index/bars")

    def get_checksum(self, partition_key: str) -> str:
        """Get checksum for partition."""
        return self._store.get_checksum(self._dataset, partition_key)
