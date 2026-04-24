"""Backtest — 回测引擎模块。"""

from ditto_engine.backtest.config import EngineConfig, EngineMode
from ditto_engine.backtest.data_feed import (
    DataFeed,
    ProviderBackedDataFeed,
    Slice,
)
from ditto_engine.backtest.engine import (
    EngineLoop,
    EngineResult,
)
from ditto_engine.backtest.manifest import (
    InputRef,
    RuleRef,
    RuleRefCollector,
    RunManifest,
    RunMode,
    build_run_manifest,
    hash_spec,
    serialize_manifest,
)
from ditto_engine.backtest.protocol import TradingLoop
from ditto_engine.backtest.report_renderer import BacktestReportRenderer
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
    "BacktestReportRenderer",
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
    "TradingLoop",
    "build_run_manifest",
    "hash_spec",
    "serialize_manifest",
]
