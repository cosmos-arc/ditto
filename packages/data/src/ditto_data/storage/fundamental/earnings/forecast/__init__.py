"""EarningsForecast parquet storage."""

from ditto_data.storage.fundamental.earnings.forecast.reader import (
    EarningsForecastReader,
)
from ditto_data.storage.fundamental.earnings.forecast.writer import (
    EarningsForecastWriter,
)

__all__ = ["EarningsForecastReader", "EarningsForecastWriter"]
