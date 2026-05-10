"""
etf_rotation 策略模板 -- ETF 动量轮动的 alpha stages.

标准流程:
  Signal -> Score -> RiskLockFilter -> Select
  (可选: RegimeScoringStep -> RegimeAwareAllocationStage)

提供:
- ETFRotationConfig: 策略模板运行时配置
- validate_config: 配置校验
- get_param_constraints: 参数扫描元数据
- build_etf_rotation_pipeline: 组装 alpha stages
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
from ditto_strategy.alpha.specs import ParamConstraint
from ditto_strategy.alpha.templates._common import raise_config_error

__all__ = [
    "ETFRotationConfig",
    "build_etf_rotation_pipeline",
    "get_param_constraints",
    "validate_config",
]


def _raise_config_error(
    message: str,
    *,
    field_name: str,
    reason: str,
    actual_value: object,
    **details: object,
) -> None:
    """Raise a template config error with consistent metadata."""
    raise_config_error(
        message,
        template="etf_rotation",
        field_name=field_name,
        reason=reason,
        actual_value=actual_value,
        **details,
    )


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


# ---------------------------------------------------------------------------
# validate_config
# ---------------------------------------------------------------------------


def validate_config(config: ETFRotationConfig) -> None:
    """
    校验 ETFRotationConfig 合法性.

    Raises:
        StrategySpecError: 配置不合法时抛出描述性异常。

    """
    if config.top_k < 1:
        msg = f"top_k must be >= 1, got {config.top_k}"
        _raise_config_error(
            msg,
            field_name="top_k",
            reason="below_min",
            actual_value=config.top_k,
            min_value=1,
        )

    if config.max_weight is not None and (
        config.max_weight <= 0 or config.max_weight > 1
    ):
        msg = f"max_weight must be > 0 and <= 1, got {config.max_weight}"
        _raise_config_error(
            msg,
            field_name="max_weight",
            reason="out_of_range",
            actual_value=config.max_weight,
            min_value=0,
            max_value=1,
        )

    valid_methods = ("equal_weight", "score_weight")
    if config.allocation_method not in valid_methods:
        msg = (
            f"allocation_method must be one of {valid_methods}, "
            f"got '{config.allocation_method}'"
        )
        _raise_config_error(
            msg,
            field_name="allocation_method",
            reason="invalid_enum",
            actual_value=config.allocation_method,
            allowed_values=valid_methods,
        )

    if config.cash_target < 0 or config.cash_target >= 1:
        msg = f"cash_target must be >= 0 and < 1, got {config.cash_target}"
        _raise_config_error(
            msg,
            field_name="cash_target",
            reason="out_of_range",
            actual_value=config.cash_target,
            min_value=0,
            max_value=1,
        )


# ---------------------------------------------------------------------------
# get_param_constraints
# ---------------------------------------------------------------------------


def get_param_constraints() -> tuple[ParamConstraint, ...]:
    """
    返回 etf_rotation 模板的参数扫描元数据.

    Returns:
        ParamConstraint 元组，描述可调参数的范围和可选值。

    """
    return (
        ParamConstraint(
            name="top_k",
            dtype="int",
            min_value=1,
            max_value=100,
            step=1,
        ),
        ParamConstraint(
            name="cash_target",
            dtype="float",
            min_value=0.0,
            max_value=0.5,
            step=0.05,
        ),
        ParamConstraint(
            name="allocation_method",
            dtype="str",
            allowed_values=("equal_weight", "score_weight"),
        ),
    )


# ---------------------------------------------------------------------------
# build_etf_rotation_pipeline
# ---------------------------------------------------------------------------


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
