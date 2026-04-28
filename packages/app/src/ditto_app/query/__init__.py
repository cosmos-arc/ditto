"""
App Query 模块 — 只读查询，零副作用.

公共 API（4 个核心 Facade）:
- BacktestQueryFacade, StrategyQueryFacade, TradeQueryFacade, ComparisonQueryFacade

其余查询门面请直接从叶模块导入。
"""

from __future__ import annotations

from ditto_app.query.backtest import BacktestQueryFacade
from ditto_app.query.comparison import ComparisonQueryFacade
from ditto_app.query.strategy import StrategyQueryFacade
from ditto_app.query.trade import TradeQueryFacade

__all__ = [
    "BacktestQueryFacade",
    "ComparisonQueryFacade",
    "StrategyQueryFacade",
    "TradeQueryFacade",
]
