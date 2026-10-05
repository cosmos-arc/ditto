"""EarningsForecast parquet writer."""

from ditto_data.storage.base.dataset_writer import ParquetDatasetWriter
from ditto_platform.foundation import ParquetStore


class EarningsForecastWriter(ParquetDatasetWriter):
    """Write fundamental/earnings_forecast facts."""

    def __init__(self, store: ParquetStore) -> None:
        super().__init__(store, "fundamental/earnings_forecast")
