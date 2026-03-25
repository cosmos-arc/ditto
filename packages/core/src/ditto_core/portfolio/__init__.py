"""
Portfolio — 组合管理模块.

提供权重分配（WeightAllocator）、约束检查（ConstraintChecker）和策略对比（StrategyComparisonReport），
通过 AllocationStage / ConstraintStage 适配为 DecisionStage Protocol。
"""

from ditto_core.portfolio.allocation import (
    AllocationStage,
    EqualWeightAllocator,
    InverseVolAllocator,
    ScoreWeightAllocator,
    WeightAllocator,
)
from ditto_core.portfolio.comparison import (
    MetricsDelta,
    StrategyComparisonReport,
    compare_reports,
)
from ditto_core.portfolio.constraints import (
    Constraint,
    ConstraintAdjustment,
    ConstraintChecker,
    ConstraintStage,
    MaxPositionsConstraint,
    MaxWeightConstraint,
    MinWeightConstraint,
)
from ditto_core.portfolio.report_views import (
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
    "InverseVolAllocator",
    "MaxPositionsConstraint",
    "MaxWeightConstraint",
    "MetricsDelta",
    "MinWeightConstraint",
    "ScoreWeightAllocator",
    "StrategyComparisonReport",
    "WeightAllocator",
    "compare_reports",
]
