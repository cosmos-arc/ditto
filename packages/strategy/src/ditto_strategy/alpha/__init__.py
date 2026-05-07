"""
Alpha — 策略决策层（因子 Alpha 生成）.

公共 API:
- StrategyPipeline, StrategySpec, StrategyRun, TargetPortfolio, StrategyContext
- StrategyInputBundle, DecisionStage, RegimeStage, StrategyTemplate

其余类型（builtins/specs/models 等）请直接从叶模块导入。
"""

from ditto_strategy.alpha.builtins.regime import RegimeStage
from ditto_strategy.alpha.context import StrategyContext
from ditto_strategy.alpha.models import StrategyRun, StrategyTemplate, TargetPortfolio
from ditto_strategy.alpha.pipeline import StrategyInputBundle, StrategyPipeline
from ditto_strategy.alpha.protocols import DecisionStage
from ditto_strategy.alpha.specs import StrategySpec

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
