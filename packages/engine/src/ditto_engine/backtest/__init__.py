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
    InputRef,
    RuleRef,
    RuleRefCollector,
    RunManifest,
    RunMode,
    hash_spec,
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
    "InputRef",
    "PortfolioStatistics",
    "ProviderBackedDataFeed",
    "RuleRef",
    "RuleRefCollector",
    "RunManifest",
    "RunMode",
    "Slice",
    "TradeStatistics",
    "hash_spec",
    "serialize_manifest",
]
