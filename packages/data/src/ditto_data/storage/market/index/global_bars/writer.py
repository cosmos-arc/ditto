"""Global index daily bars writer."""

from ditto_platform.foundation import ParquetStore

from ditto_data.storage.base.dataset_writer import ParquetDatasetWriter


class GlobalIndexBarsWriter(ParquetDatasetWriter):
    """Write global index bars without inventing local instrument IDs."""

    def __init__(self, store: ParquetStore) -> None:
        super().__init__(store, "market/index/global_bars")
