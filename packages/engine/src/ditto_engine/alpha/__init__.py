"""
Alpha — 策略决策层（因子 Alpha 生成）.

specs, models, context, protocols, pipeline, builtins, templates.

Note: 模板（ETFRotationConfig 等）从 ditto_engine.alpha.templates 导入，
避免 portfolio ↔ alpha 循环依赖。
"""

from ditto_engine.alpha.builtins import (
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
from ditto_engine.alpha.context import StrategyContext
from ditto_engine.alpha.models import (
    RebalancePlan,
    SignalSnapshot,
    StrategyRun,
    StrategyTemplate,
    StrategyVersion,
    TargetPortfolio,
)
from ditto_engine.alpha.pipeline import StrategyInputBundle, StrategyPipeline
from ditto_engine.alpha.protocols import DecisionStage
from ditto_engine.alpha.specs import (
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
