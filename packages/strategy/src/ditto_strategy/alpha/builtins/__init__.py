"""
Built-in Pipeline stages.

提供开箱即用的 DecisionStage 实现:

- UniverseStage: instrument_id 白名单过滤
- SignalStage: 信号列 attach
- ScoringStage + ScoringMethod: signal -> score 转换
- FilteringStage + FilterCondition: 条件过滤
- RiskLockFilter: 风控锁定过滤
- TrendFilterStage: 趋势方向过滤
- SelectionStage: top K 选取

Regime 相关符号（RegimeStage / RegimeMethod / RegimeLabel / RegimeConfig 等）
请直接从子模块导入::

    from ditto_strategy.alpha.builtins.regime import RegimeStage
    from ditto_strategy.alpha.builtins.regime_allocation import (
        RegimeAwareAllocationStage,
    )
    from ditto_strategy.alpha.builtins.regime_scoring import RegimeScoringStep
"""

from ditto_strategy.alpha.builtins.filtering import (
    FilterCondition,
    FilteringStage,
    RiskLockFilter,
    TrendFilterStage,
)
from ditto_strategy.alpha.builtins.scoring import ScoringMethod, ScoringStage
from ditto_strategy.alpha.builtins.selection import SelectionStage
from ditto_strategy.alpha.builtins.signal import SignalStage
from ditto_strategy.alpha.builtins.universe import UniverseStage

__all__ = [
    "FilterCondition",
    "FilteringStage",
    "RiskLockFilter",
    "ScoringMethod",
    "ScoringStage",
    "SelectionStage",
    "SignalStage",
    "TrendFilterStage",
    "UniverseStage",
]
