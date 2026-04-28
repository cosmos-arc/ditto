"""FX daily bars reader."""

from ditto_data.storage.base import ParquetStore
from ditto_data.storage.base.dataset_reader import ParquetDatasetReader


class FxBarsReader(ParquetDatasetReader):
    """Reader for FX daily bars data."""

    def __init__(self, store: ParquetStore) -> None:
        super().__init__(store, "market/fx/bars")
