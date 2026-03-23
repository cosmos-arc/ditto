"""Backtest — 回测引擎模块。"""

from ditto_core.backtest.data_feed import (
    DataFeed,
    ParquetDataFeed,
    Slice,
)
from ditto_core.backtest.engine import (
    EngineConfig,
    EngineLoop,
    EngineMode,
    EngineResult,
)
from ditto_core.backtest.manifest import (
    RuleRef,
    RuleRefCollector,
    RunManifest,
    RunMode,
    serialize_manifest,
)
from ditto_core.backtest.risk.post_trade import (
    CompositePostTradeGuard,
    PostTradeRiskGuard,
    RiskAction,
    RiskActionType,
)
from ditto_core.backtest.risk.pre_trade import (
    CompositePreTradeCheck,
    Decision,
    OrderCheckResult,
    PreTradeContext,
    PreTradeRiskCheck,
)
from ditto_core.backtest.statistics import (
    AggregatedTradeStatistics,
    AlphaStatistics,
    BacktestReport,
    ExecutionAuditCollector,
    PortfolioStatistics,
    TradeStatistics,
)
from ditto_core.execution.reality.market import MarketSnapshot

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
    "ParquetDataFeed",
    "PortfolioStatistics",
    "PostTradeRiskGuard",
    "PreTradeContext",
    "PreTradeRiskCheck",
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
