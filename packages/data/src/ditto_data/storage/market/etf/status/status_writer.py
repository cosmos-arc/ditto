"""ETF status writer."""

from ditto_platform.foundation.storage import ParquetStore

from ditto_data.storage.base.dataset_writer import ParquetDatasetWriter


class EtfStatusWriter(ParquetDatasetWriter):
    """Writer for ETF status data."""

    def __init__(self, store: ParquetStore) -> None:
        super().__init__(store, "market/etf/status")

    def get_checksum(self, partition_key: str) -> str:
        """Get checksum for partition."""
        return self._store.get_checksum(self._dataset, partition_key)
