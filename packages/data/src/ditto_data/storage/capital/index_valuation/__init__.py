"""IndexValuation parquet storage."""

from ditto_data.storage.capital.index_valuation.reader import IndexValuationReader
from ditto_data.storage.capital.index_valuation.writer import IndexValuationWriter

__all__ = ["IndexValuationReader", "IndexValuationWriter"]
