"""
stock_selection_trend 配置、校验与参数约束.

提供:
- StockSelectionTrendConfig: 策略模板运行时配置
- validate_config: 配置校验
- get_param_constraints: 参数扫描元数据
"""

from __future__ import annotations

from dataclasses import dataclass

from ditto_strategy.alpha.builtins.regime import RegimeConfig
from ditto_strategy.alpha.specs import ParamConstraint
from ditto_strategy.alpha.templates._common import raise_config_error

__all__ = [
    "StockSelectionTrendConfig",
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
        template="stock_selection_trend",
        field_name=field_name,
        reason=reason,
        actual_value=actual_value,
        **details,
    )


# ---------------------------------------------------------------------------
# StockSelectionTrendConfig
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StockSelectionTrendConfig:
    """
    stock_selection_trend 策略模板的运行时配置.

    Attributes:
        universe_filter: Universe 过滤条件名（预留）。
        signal_factors: 因子列名列表，从 signal_values DataFrame 中读取。
        signal_weights: 因子权重列表，须与 signal_factors 长度一致。
        top_k: 选取排名前 K 的标的。
        max_weight: 单标的最大权重。
        allocation_method: 分配方式 (``"equal_weight"`` / ``"inverse_vol"``)。
        cash_target: 目标现金比例。
        trend_threshold: 趋势过滤阈值。
        rebalance_freq: 调仓频率 (``"daily"`` / ``"weekly"`` / ``"monthly"``)。
        winsorize_sigma: 因子去极值 sigma 倍数(正值);``None`` 关闭预处理。
        zscore: 是否对因子列做 zscore 标准化。
        neutralize_by: 中性化分组列名(如 ``"industry"``);``None`` 关闭。
        fusion: 多因子融合模式(``"simple"`` 单 stage rank 加权 / ``"composite"``
            CompositeDecisionStage 子 stage 融合,产 ``score`` 列)。
        regime_config: Regime 评分配置（None = 不使用 regime 缩放）。

    """

    universe_filter: str = ""
    signal_factors: tuple[str, ...] = ("signal_value",)
    signal_weights: tuple[float, ...] = (1.0,)
    top_k: int = 10
    max_weight: float = 0.15
    allocation_method: str = "equal_weight"
    cash_target: float = 0.0
    trend_threshold: float = 0.0
    rebalance_freq: str = "daily"
    winsorize_sigma: float | None = None
    zscore: bool = False
    neutralize_by: str | None = None
    fusion: str = "simple"
    regime_config: RegimeConfig | None = None


# ---------------------------------------------------------------------------
# validate_config
# ---------------------------------------------------------------------------


def validate_config(config: StockSelectionTrendConfig) -> None:
    """
    校验 StockSelectionTrendConfig 合法性.

    Raises:
        StrategySpecError: 配置不合法时抛出描述性异常。

    """
    if len(config.signal_factors) != len(config.signal_weights):
        msg = (
            f"signal_factors (len={len(config.signal_factors)}) and "
            f"signal_weights (len={len(config.signal_weights)}) "
            f"must have the same length"
        )
        _raise_config_error(
            msg,
            field_name="signal_weights",
            reason="length_mismatch",
            actual_value=config.signal_weights,
            signal_factor_count=len(config.signal_factors),
            signal_weight_count=len(config.signal_weights),
        )

    if config.top_k < 1:
        msg = f"top_k must be >= 1, got {config.top_k}"
        _raise_config_error(
            msg,
            field_name="top_k",
            reason="below_min",
            actual_value=config.top_k,
            min_value=1,
        )

    if config.max_weight <= 0 or config.max_weight > 1:
        msg = f"max_weight must be > 0 and <= 1, got {config.max_weight}"
        _raise_config_error(
            msg,
            field_name="max_weight",
            reason="out_of_range",
            actual_value=config.max_weight,
            min_value=0,
            max_value=1,
        )

    valid_methods = ("equal_weight", "inverse_vol")
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

    valid_freqs = ("daily", "weekly", "monthly")
    if config.rebalance_freq not in valid_freqs:
        msg = (
            f"rebalance_freq must be one of {valid_freqs}, "
            f"got '{config.rebalance_freq}'"
        )
        _raise_config_error(
            msg,
            field_name="rebalance_freq",
            reason="invalid_enum",
            actual_value=config.rebalance_freq,
            allowed_values=valid_freqs,
        )

    if config.winsorize_sigma is not None and config.winsorize_sigma <= 0:
        msg = f"winsorize_sigma must be > 0, got {config.winsorize_sigma}"
        _raise_config_error(
            msg,
            field_name="winsorize_sigma",
            reason="out_of_range",
            actual_value=config.winsorize_sigma,
            min_value=0,
        )

    if config.neutralize_by is not None and not config.neutralize_by.strip():
        msg = (
            f"neutralize_by must be a non-empty column name, "
            f"got {config.neutralize_by!r}"
        )
        _raise_config_error(
            msg,
            field_name="neutralize_by",
            reason="empty_value",
            actual_value=config.neutralize_by,
        )

    valid_fusions = ("simple", "composite")
    if config.fusion not in valid_fusions:
        msg = f"fusion must be one of {valid_fusions}, got '{config.fusion}'"
        _raise_config_error(
            msg,
            field_name="fusion",
            reason="invalid_enum",
            actual_value=config.fusion,
            allowed_values=valid_fusions,
        )


# ---------------------------------------------------------------------------
# get_param_constraints
# ---------------------------------------------------------------------------


def get_param_constraints() -> tuple[ParamConstraint, ...]:
    """
    返回 stock_selection_trend 模板的参数扫描元数据.

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
            name="max_weight",
            dtype="float",
            min_value=0.01,
            max_value=1.0,
            step=0.01,
        ),
        ParamConstraint(
            name="trend_threshold",
            dtype="float",
            min_value=0.0,
            max_value=0.2,
            step=0.01,
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
            allowed_values=("equal_weight", "inverse_vol"),
        ),
        ParamConstraint(
            name="rebalance_freq",
            dtype="str",
            allowed_values=("daily", "weekly", "monthly"),
        ),
    )
