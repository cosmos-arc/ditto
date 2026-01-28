"""
Stock adjustment factor (复权因子) domain.

包含股票复权因子的存储和访问功能。
"""

from ditto_datahub.domains.market.stock.adj.adj_factor_store import (
    StockAdjFactorStore,
)

__all__ = ["StockAdjFactorStore"]
