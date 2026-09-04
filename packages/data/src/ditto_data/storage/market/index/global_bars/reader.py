"""Global index daily bars reader."""

from ditto_platform.foundation import ParquetStore

from ditto_data.storage.base.dataset_reader import ParquetDatasetReader


class GlobalIndexBarsReader(ParquetDatasetReader):
    """Read global index bars keyed by provider ticker and knowledge date."""

    def __init__(self, store: ParquetStore) -> None:
        super().__init__(store, "market/index/global_bars")
