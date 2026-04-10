"""Stock adjustment factor (复权因子) domain."""

from ditto_data.storage.market.stock.adj.adj_factor_reader import (
    StockAdjFactorReader,
)
from ditto_data.storage.market.stock.adj.adj_factor_writer import (
    StockAdjFactorWriter,
)

__all__ = [
    "StockAdjFactorReader",
    "StockAdjFactorWriter",
]
