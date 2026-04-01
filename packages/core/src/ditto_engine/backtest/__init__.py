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
from ditto_engine.backtest.risk.post_trade import (
    CompositePostTradeGuard,
    PostTradeRiskGuard,
    RiskAction,
    RiskActionType,
)
from ditto_engine.backtest.risk.pre_trade import (
    CompositePreTradeCheck,
    Decision,
    OrderCheckResult,
    PreTradeContext,
    PreTradeRiskCheck,
)
from ditto_engine.backtest.statistics import (
    AggregatedTradeStatistics,
    AlphaStatistics,
    BacktestReport,
    ExecutionAuditCollector,
    PortfolioStatistics,
    TradeStatistics,
)
from ditto_engine.execution.reality.market import MarketSnapshot

__all__ = [
    "AggregatedTradeStatistics",
    "AlphaStatistics",
    "BacktestReport",
    "CompositePostTradeGuard",
    "CompositePreTradeCheck",
    "DataFeed",
    "Decision",
    "EngineConfig",
    "EngineLoop",
    "EngineMode",
    "EngineResult",
    "ExecutionAuditCollector",
    "MarketSnapshot",
    "OrderCheckResult",
    "PortfolioStatistics",
    "PostTradeRiskGuard",
    "PreTradeContext",
    "PreTradeRiskCheck",
    "ProviderBackedDataFeed",
    "RiskAction",
    "RiskActionType",
    "RuleRef",
    "RuleRefCollector",
    "RunManifest",
    "RunMode",
    "Slice",
    "TradeStatistics",
    "serialize_manifest",
]
