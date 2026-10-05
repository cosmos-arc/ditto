"""EarningsExpress parquet writer."""

from ditto_data.storage.base.dataset_writer import ParquetDatasetWriter
from ditto_platform.foundation import ParquetStore


class EarningsExpressWriter(ParquetDatasetWriter):
    """Write fundamental/earnings_express facts."""

    def __init__(self, store: ParquetStore) -> None:
        super().__init__(store, "fundamental/earnings_express")
