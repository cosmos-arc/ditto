"""
Built-in Pipeline stages.

提供 9 个开箱即用的 DecisionStage 实现:

- UniverseStage: instrument_id 白名单过滤
- SignalStage: 信号列 attach
- ScoringStage + ScoringMethod: signal -> score 转换
- FilteringStage + FilterCondition: 条件过滤
- RiskLockFilter: 风控锁定过滤
- TrendFilterStage: 趋势方向过滤
- SelectionStage: top K 选取
- RegimeStage + RegimeMethod + RegimeLabel: 市场状态检测
- RegimeAwareAllocationStage: Regime 感知仓位缩放
- RegimeScoringStep: Regime 评分 Step
"""

from ditto_engine.alpha.builtins.filtering import (
    FilterCondition,
    FilteringStage,
    RiskLockFilter,
    TrendFilterStage,
)
from ditto_engine.alpha.builtins.regime import (
    BreadthIndicator,
    MomentumIndicator,
    RegimeConfig,
    RegimeIndicator,
    RegimeLabel,
    RegimeMethod,
    RegimeResult,
    RegimeScoreEngine,
    RegimeStage,
    TrendIndicator,
    VolatilityIndicator,
)
from ditto_engine.alpha.builtins.regime_allocation import (
    RegimeAwareAllocationStage,
)
from ditto_engine.alpha.builtins.regime_scoring import RegimeScoringStep
from ditto_engine.alpha.builtins.scoring import ScoringMethod, ScoringStage
from ditto_engine.alpha.builtins.selection import SelectionStage
from ditto_engine.alpha.builtins.signal import SignalStage
from ditto_engine.alpha.builtins.universe import UniverseStage

__all__ = [
    "BreadthIndicator",
    "FilterCondition",
    "FilteringStage",
    "MomentumIndicator",
    "RegimeAwareAllocationStage",
    "RegimeConfig",
    "RegimeIndicator",
    "RegimeLabel",
    "RegimeMethod",
    "RegimeResult",
    "RegimeScoreEngine",
    "RegimeScoringStep",
    "RegimeStage",
    "RiskLockFilter",
    "ScoringMethod",
    "ScoringStage",
    "SelectionStage",
    "SignalStage",
    "TrendFilterStage",
    "TrendIndicator",
    "UniverseStage",
    "VolatilityIndicator",
]
