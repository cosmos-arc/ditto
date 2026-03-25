"""
Built-in Pipeline stages.

提供 8 个开箱即用的 DecisionStage 实现:

- UniverseStage: instrument_id 白名单过滤
- SignalStage: 信号列 attach
- ScoringStage + ScoringMethod: signal -> score 转换
- FilteringStage + FilterCondition: 条件过滤
- RiskLockFilter: 风控锁定过滤
- TrendFilterStage: 趋势方向过滤
- SelectionStage: top K 选取
- RegimeStage + RegimeMethod + RegimeLabel: 市场状态检测
"""

from ditto_core.strategy.builtins.filtering import (
    FilterCondition,
    FilteringStage,
    RiskLockFilter,
    TrendFilterStage,
)
from ditto_core.strategy.builtins.regime import (
    RegimeLabel,
    RegimeMethod,
    RegimeStage,
)
from ditto_core.strategy.builtins.scoring import ScoringMethod, ScoringStage
from ditto_core.strategy.builtins.selection import SelectionStage
from ditto_core.strategy.builtins.signal import SignalStage
from ditto_core.strategy.builtins.universe import UniverseStage

__all__ = [
    "FilterCondition",
    "FilteringStage",
    "RegimeLabel",
    "RegimeMethod",
    "RegimeStage",
    "RiskLockFilter",
    "ScoringMethod",
    "ScoringStage",
    "SelectionStage",
    "SignalStage",
    "TrendFilterStage",
    "UniverseStage",
]
