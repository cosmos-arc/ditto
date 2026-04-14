"""
Alpha — 策略决策层（因子 Alpha 生成）.

公共 API:
- StrategyPipeline, StrategySpec, StrategyRun, TargetPortfolio, StrategyContext
- StrategyInputBundle, DecisionStage, RegimeStage, StrategyTemplate

其余类型（builtins/specs/models 等）请直接从叶模块导入。
"""

from ditto_engine.alpha.builtins.regime import RegimeStage
from ditto_engine.alpha.context import StrategyContext
from ditto_engine.alpha.models import StrategyRun, StrategyTemplate, TargetPortfolio
from ditto_engine.alpha.pipeline import StrategyInputBundle, StrategyPipeline
from ditto_engine.alpha.protocols import DecisionStage
from ditto_engine.alpha.specs import StrategySpec

__all__ = [
    "DecisionStage",
    "RegimeStage",
    "StrategyContext",
    "StrategyInputBundle",
    "StrategyPipeline",
    "StrategyRun",
    "StrategySpec",
    "StrategyTemplate",
    "TargetPortfolio",
]
