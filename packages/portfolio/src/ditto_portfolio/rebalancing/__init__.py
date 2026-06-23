"""
Portfolio — 组合管理模块.

提供权重分配（WeightAllocator）、约束检查（ConstraintChecker）和策略对比（StrategyComparisonReport），
通过 AllocationStage / ConstraintStage 适配为 DecisionStage Protocol。
"""

from ditto_portfolio.rebalancing.allocation import (
    AllocationStage,
    EqualWeightAllocator,
    InverseVolAllocator,
    ScoreWeightAllocator,
    WeightAllocator,
)
from ditto_portfolio.rebalancing.comparison import (
    MetricsDelta,
    StrategyComparisonReport,
    compare_reports,
)
from ditto_portfolio.rebalancing.constraints import (
    Constraint,
    ConstraintAdjustment,
    ConstraintChecker,
    ConstraintStage,
    IndustryMaxWeightConstraint,
    LiquidityConstraint,
    MaxPositionsConstraint,
    MaxTurnoverConstraint,
    MaxWeightConstraint,
    MinWeightConstraint,
    TradabilityConstraint,
)
from ditto_portfolio.rebalancing.report_views import (
    AggregatedTradeStatsView,
    AlphaStatsView,
    BacktestReportView,
)

__all__ = [
    "AggregatedTradeStatsView",
    "AllocationStage",
    "AlphaStatsView",
    "BacktestReportView",
    "Constraint",
    "ConstraintAdjustment",
    "ConstraintChecker",
    "ConstraintStage",
    "EqualWeightAllocator",
    "IndustryMaxWeightConstraint",
    "InverseVolAllocator",
    "LiquidityConstraint",
    "MaxPositionsConstraint",
    "MaxTurnoverConstraint",
    "MaxWeightConstraint",
    "MetricsDelta",
    "MinWeightConstraint",
    "ScoreWeightAllocator",
    "StrategyComparisonReport",
    "TradabilityConstraint",
    "WeightAllocator",
    "compare_reports",
]
