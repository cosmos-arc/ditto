"""EarningsForecast parquet reader."""

from ditto_data.storage.base.dataset_reader import ParquetDatasetReader
from ditto_platform.foundation import ParquetStore


class EarningsForecastReader(ParquetDatasetReader):
    """Read fundamental/earnings_forecast facts."""

    def __init__(self, store: ParquetStore) -> None:
        super().__init__(store, "fundamental/earnings_forecast")
