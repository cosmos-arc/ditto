"""
Strategy — 策略决策层.

Phase 0: specs, models, context, protocols.
Phase 1: pipeline, builtins, templates.

Note: 模板（ETFRotationConfig 等）从 ditto_engine.strategy.templates 导入，
避免 portfolio ↔ strategy 循环依赖。
"""

from ditto_engine.strategy.builtins import (
    FilterCondition,
    FilteringStage,
    RegimeLabel,
    RegimeMethod,
    RegimeStage,
    RiskLockFilter,
    ScoringMethod,
    ScoringStage,
    SelectionStage,
    SignalStage,
    TrendFilterStage,
    UniverseStage,
)
from ditto_engine.strategy.context import StrategyContext
from ditto_engine.strategy.models import (
    RebalancePlan,
    SignalSnapshot,
    StrategyRun,
    StrategyTemplate,
    StrategyVersion,
    TargetPortfolio,
)
from ditto_engine.strategy.pipeline import StrategyInputBundle, StrategyPipeline
from ditto_engine.strategy.protocols import DecisionStage
from ditto_engine.strategy.specs import (
    ConstraintSpec,
    CostModelSpec,
    ExecutionSpec,
    ParamConstraint,
    ScorerSpec,
    SelectorSpec,
    StrategySpec,
)

__all__ = [
    "ConstraintSpec",
    "CostModelSpec",
    "DecisionStage",
    "ExecutionSpec",
    "FilterCondition",
    "FilteringStage",
    "ParamConstraint",
    "RebalancePlan",
    "RegimeLabel",
    "RegimeMethod",
    "RegimeStage",
    "RiskLockFilter",
    "ScorerSpec",
    "ScoringMethod",
    "ScoringStage",
    "SelectionStage",
    "SelectorSpec",
    "SignalSnapshot",
    "SignalStage",
    "StrategyContext",
    "StrategyInputBundle",
    "StrategyPipeline",
    "StrategyRun",
    "StrategySpec",
    "StrategyTemplate",
    "StrategyVersion",
    "TargetPortfolio",
    "TrendFilterStage",
    "UniverseStage",
]
