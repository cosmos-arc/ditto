"""
etf_rotation 策略模板 -- ETF 动量轮动的 alpha stages.

标准流程:
  Signal -> Score -> RiskLockFilter -> Select
  (可选: RegimeScoringStep -> RegimeAwareAllocationStage)
"""

from __future__ import annotations

from dataclasses import dataclass

from ditto_strategy.alpha.builtins.filtering import RiskLockFilter
from ditto_strategy.alpha.builtins.regime import RegimeConfig
from ditto_strategy.alpha.builtins.regime_allocation import (
    RegimeAwareAllocationStage,
)
from ditto_strategy.alpha.builtins.regime_scoring import RegimeScoringStep
from ditto_strategy.alpha.builtins.scoring import ScoringMethod, ScoringStage
from ditto_strategy.alpha.builtins.selection import SelectionStage
from ditto_strategy.alpha.builtins.signal import SignalStage
from ditto_strategy.alpha.protocols import DecisionStage

__all__ = ["ETFRotationConfig", "build_etf_rotation_pipeline"]


@dataclass(frozen=True)
class ETFRotationConfig:
    """
    etf_rotation 策略模板的运行时配置.

    Attributes:
        top_k: 选取标的数量。
        scoring_method: 评分方法。
        scoring_ascending: True 表示信号值大的得分高（动量策略默认 True）。
        allocation_method: 分配方式（``"equal_weight"`` / ``"score_weight"``）。
        cash_target: 目标现金比例（0.0 = 全仓）。
        signal_column: 信号源列名。
        max_weight: 单标的权重上限（None = 不限制）。
        max_positions: 最大持仓数量（None = 不限制）。
        regime_config: Regime 评分配置（None = 不使用 regime 缩放）。

    """

    top_k: int = 10
    scoring_method: ScoringMethod = ScoringMethod.RANK
    scoring_ascending: bool = True
    allocation_method: str = "equal_weight"
    cash_target: float = 0.0
    signal_column: str = "signal_value"
    max_weight: float | None = None
    max_positions: int | None = None
    regime_config: RegimeConfig | None = None


def build_etf_rotation_pipeline(
    config: ETFRotationConfig,
) -> list[DecisionStage]:
    """
    组装 etf_rotation 的 alpha stages.

    标准流程:
      Signal -> Score -> RiskLockFilter -> Select -> [Regime]

    分配与约束由 application 层根据 config 参数独立配置。

    Args:
        config: 运行时配置。

    Returns:
        alpha DecisionStage 列表。

    """
    stages: list[DecisionStage] = [
        SignalStage(source_column=config.signal_column),
        ScoringStage(method=config.scoring_method, ascending=config.scoring_ascending),
        RiskLockFilter(),
        SelectionStage(top_k=config.top_k),
    ]

    # Regime-aware allocation (optional, strategy-internal)
    if config.regime_config is not None:
        stages.append(RegimeScoringStep(config.regime_config))
        stages.append(RegimeAwareAllocationStage())

    return stages
