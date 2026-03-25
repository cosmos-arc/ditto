"""
Execution — 执行层类型定义.

Phase 0: rules (三层规则), fills (FillOutcome).
Phase 2: brokerage, trade_builder, planner, reality/.
Phase 3: ProcessInput, MarketSnapshot (moved from backtest).
"""

from ditto_core.execution.brokerage import BacktestBrokerage, Brokerage, ProcessInput
from ditto_core.execution.fills import (
    Filled,
    FillEvent,
    FillOutcome,
    NoFill,
)
from ditto_core.execution.orders import (
    Order,
    OrderBook,
    OrderBookReadOnly,
    OrderDirection,
    OrderEvent,
    OrderStatus,
    OrderTicket,
    OrderType,
)
from ditto_core.execution.planner import (
    BlockedOrder,
    BlockSeverity,
    ExecutionPlan,
    ExecutionPlanner,
    SimpleExecutionPlanner,
)
from ditto_core.execution.reality import (
    AShareFeeModel,
    AShareFillModel,
    AShareSettlementModel,
    BrokerageModel,
    ClosingAuctionFillModel,
    FeeModel,
    FillModel,
    FixedBpsSlippage,
    MarketSnapshot,
    SettlementModel,
    SimpleFeeModel,
    SimpleFillModel,
    SimpleSettlementModel,
    SlippageModel,
    VolumeShareSlippage,
)
from ditto_core.execution.rules import (
    FeeSchedule,
    InMemoryRuleProvider,
    InstrumentDefinition,
    InstrumentRuleProvider,
    InstrumentRules,
    RulesGetter,
    TradingRuleSet,
    default_price_limit_pct,
)
from ditto_core.execution.targets import TargetPortfolioLike
from ditto_core.execution.trade_builder import (
    FifoTradeBuilder,
    FlatToFlatTradeBuilder,
    TradeBuilder,
    TradeMatchingMethod,
    TradeRecord,
)

__all__ = [
    "AShareFeeModel",
    "AShareFillModel",
    "AShareSettlementModel",
    "BacktestBrokerage",
    "BlockSeverity",
    "BlockedOrder",
    "Brokerage",
    "BrokerageModel",
    "ClosingAuctionFillModel",
    "ExecutionPlan",
    "ExecutionPlanner",
    "FeeModel",
    "FeeSchedule",
    "FifoTradeBuilder",
    "FillEvent",
    "FillModel",
    "FillOutcome",
    "Filled",
    "FixedBpsSlippage",
    "FlatToFlatTradeBuilder",
    "InMemoryRuleProvider",
    "InstrumentDefinition",
    "InstrumentRuleProvider",
    "InstrumentRules",
    "MarketSnapshot",
    "NoFill",
    "Order",
    "OrderBook",
    "OrderBookReadOnly",
    "OrderDirection",
    "OrderEvent",
    "OrderStatus",
    "OrderTicket",
    "OrderType",
    "ProcessInput",
    "RulesGetter",
    "SettlementModel",
    "SimpleExecutionPlanner",
    "SimpleFeeModel",
    "SimpleFillModel",
    "SimpleSettlementModel",
    "SlippageModel",
    "TargetPortfolioLike",
    "TradeBuilder",
    "TradeMatchingMethod",
    "TradeRecord",
    "TradingRuleSet",
    "VolumeShareSlippage",
    "default_price_limit_pct",
]
