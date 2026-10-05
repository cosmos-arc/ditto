"""FuturesBasic parquet storage."""

from ditto_data.storage.market.futures.basic.reader import FuturesBasicReader
from ditto_data.storage.market.futures.basic.writer import FuturesBasicWriter

__all__ = ["FuturesBasicReader", "FuturesBasicWriter"]
