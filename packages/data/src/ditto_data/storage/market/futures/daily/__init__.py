"""FuturesDaily parquet storage."""

from ditto_data.storage.market.futures.daily.reader import FuturesDailyReader
from ditto_data.storage.market.futures.daily.writer import FuturesDailyWriter

__all__ = ["FuturesDailyReader", "FuturesDailyWriter"]
