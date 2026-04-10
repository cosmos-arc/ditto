"""Backtest — 回测引擎模块。"""

from ditto_engine.backtest.data_feed import (
    DataFeed,
    ProviderBackedDataFeed,
    Slice,
)
from ditto_engine.backtest.engine import (
    EngineConfig,
    EngineLoop,
    EngineMode,
    EngineResult,
)
from ditto_engine.backtest.manifest import (
    RuleRef,
    RuleRefCollector,
    RunManifest,
    RunMode,
    serialize_manifest,
)
from ditto_engine.backtest.statistics import (
    AggregatedTradeStatistics,
    AlphaStatistics,
    BacktestReport,
    ExecutionAuditCollector,
    PortfolioStatistics,
    TradeStatistics,
)

__all__ = [
    "AggregatedTradeStatistics",
    "AlphaStatistics",
    "BacktestReport",
    "DataFeed",
    "EngineConfig",
    "EngineLoop",
    "EngineMode",
    "EngineResult",
    "ExecutionAuditCollector",
    "PortfolioStatistics",
    "ProviderBackedDataFeed",
    "RuleRef",
    "RuleRefCollector",
    "RunManifest",
    "RunMode",
    "Slice",
    "TradeStatistics",
    "serialize_manifest",
]
