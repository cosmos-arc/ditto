"""
RegimeStage -- 市场状态检测 DecisionStage.

提供:
- RegimeLabel / RegimeMethod: 枚举类型
- RegimeStage: 市场状态检测 DecisionStage（向后兼容）
- RegimeIndicator: 市场状态指标 Protocol
- TrendIndicator / VolatilityIndicator: 从 RegimeStage 提取的指标
- BreadthIndicator / MomentumIndicator: 扩展指标
- RegimeConfig / RegimeResult: 评分引擎配置与结果
- RegimeScoreEngine: 多指标加权评分引擎
"""

from __future__ import annotations

from ditto_strategy.alpha.builtins.regime.regime_engine import (
    RegimeScoreEngine,
    RegimeStage,
)
from ditto_strategy.alpha.builtins.regime.regime_indicators import (
    BreadthIndicator,
    MomentumIndicator,
    TrendIndicator,
    VolatilityIndicator,
)
from ditto_strategy.alpha.builtins.regime.regime_types import (
    RegimeConfig,
    RegimeIndicator,
    RegimeLabel,
    RegimeMethod,
    RegimeResult,
)

__all__ = [
    "BreadthIndicator",
    "MomentumIndicator",
    "RegimeConfig",
    "RegimeIndicator",
    "RegimeLabel",
    "RegimeMethod",
    "RegimeResult",
    "RegimeScoreEngine",
    "RegimeStage",
    "TrendIndicator",
    "VolatilityIndicator",
]
