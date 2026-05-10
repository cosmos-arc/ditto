"""
stock_selection_trend 策略模板 -- 多因子选股趋势追踪的 alpha stages.

标准流程:
  MultiFactorSignal -> TrendFilter -> Scoring -> RiskLockFilter ->
  Select(top_k) -> [Regime]

提供:
- StockSelectionTrendConfig: 策略模板运行时配置
- MultiFactorSignalStage: 多因子加权信号 Stage
- validate_config: 配置校验
- get_param_constraints: 参数扫描元数据
- build_stock_selection_trend_pipeline: 组装 alpha stages
"""

from __future__ import annotations

from ditto_strategy.alpha.builtins.filtering import RiskLockFilter, TrendFilterStage
from ditto_strategy.alpha.builtins.regime_allocation import (
    RegimeAwareAllocationStage,
)
from ditto_strategy.alpha.builtins.regime_scoring import RegimeScoringStep
from ditto_strategy.alpha.builtins.scoring import ScoringMethod, ScoringStage
from ditto_strategy.alpha.builtins.selection import SelectionStage
from ditto_strategy.alpha.protocols import DecisionStage
from ditto_strategy.alpha.templates.stock_selection_trend_config import (
    StockSelectionTrendConfig,
    get_param_constraints,
    validate_config,
)
from ditto_strategy.alpha.templates.stock_selection_trend_stages import (
    MultiFactorSignalStage,
)

__all__ = [
    "MultiFactorSignalStage",
    "StockSelectionTrendConfig",
    "build_stock_selection_trend_pipeline",
    "get_param_constraints",
    "validate_config",
]


# ---------------------------------------------------------------------------
# build_stock_selection_trend_pipeline
# ---------------------------------------------------------------------------


def build_stock_selection_trend_pipeline(
    config: StockSelectionTrendConfig,
) -> list[DecisionStage]:
    """
    组装 stock_selection_trend 的 alpha stages.

    流程:
      MultiFactorSignal -> TrendFilter -> Scoring -> RiskLockFilter ->
      Select(top_k) -> [Regime]

    分配与约束由 application 层根据 config 参数独立配置。

    Args:
        config: 运行时配置。

    Returns:
        alpha DecisionStage 列表。

    """
    stages: list[DecisionStage] = [
        MultiFactorSignalStage(
            signal_factors=config.signal_factors,
            signal_weights=config.signal_weights,
            output_column="signal_value",
        ),
        TrendFilterStage(
            threshold=config.trend_threshold,
            direction="long",
            signal_column="signal_value",
        ),
        ScoringStage(method=ScoringMethod.RANK, ascending=False),
        RiskLockFilter(),
        SelectionStage(top_k=config.top_k),
    ]

    # Regime-aware allocation (optional, strategy-internal)
    if config.regime_config is not None:
        stages.append(RegimeScoringStep(config.regime_config))
        stages.append(RegimeAwareAllocationStage())

    return stages
