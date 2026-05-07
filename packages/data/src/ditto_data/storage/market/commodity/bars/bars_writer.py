"""Commodity daily bars writer."""

from ditto_platform.foundation.storage import ParquetStore

from ditto_data.storage.base.dataset_writer import ParquetDatasetWriter


class CommodityBarsWriter(ParquetDatasetWriter):
    """Writer for commodity daily bars data."""

    def __init__(self, store: ParquetStore) -> None:
        super().__init__(store, "market/commodity/bars")

    def get_checksum(self, partition_key: str) -> str:
        """Get checksum for partition."""
        return self._store.get_checksum(self._dataset, partition_key)
