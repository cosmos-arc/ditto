"""FundShare parquet writer."""

from ditto_platform.foundation import ParquetStore

from ditto_data.storage.base.dataset_writer import ParquetDatasetWriter


class FundShareWriter(ParquetDatasetWriter):
    """Write market/etf/fund_share facts."""

    def __init__(self, store: ParquetStore) -> None:
        super().__init__(store, "market/etf/fund_share")
