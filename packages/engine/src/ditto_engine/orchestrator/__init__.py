"""TradingOrchestrator — 交易编排形式化抽象."""

from ditto_engine.backtest.engine import BacktestTradingOrchestrator
from ditto_engine.orchestrator.contracts import AlphaOutput, PortfolioOutput
from ditto_engine.orchestrator.protocol import TradingOrchestrator

__all__ = [
    "AlphaOutput",
    "BacktestTradingOrchestrator",
    "PortfolioOutput",
    "TradingOrchestrator",
]
