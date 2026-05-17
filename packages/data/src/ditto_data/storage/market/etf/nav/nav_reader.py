"""ETF net asset value reader."""

from ditto_platform.foundation import ParquetStore

from ditto_data.storage.base.dataset_reader import ParquetDatasetReader


class EtfNavReader(ParquetDatasetReader):
    """Reader for ETF net asset value data."""

    def __init__(self, store: ParquetStore) -> None:
        super().__init__(store, "market/etf/nav")
