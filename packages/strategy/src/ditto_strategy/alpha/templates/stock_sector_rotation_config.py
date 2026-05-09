"""
stock_sector_rotation 配置、校验与参数约束.

提供:
- StockSectorRotationConfig: 策略模板运行时配置
- validate_config: 配置校验
- get_param_constraints: 参数扫描元数据
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import NoReturn

from ditto_strategy.alpha.builtins.regime import RegimeConfig
from ditto_strategy.alpha.specs import ParamConstraint
from ditto_strategy.errors import StrategySpecError

__all__ = [
    "StockSectorRotationConfig",
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
) -> NoReturn:
    """Raise a template config error with consistent metadata."""
    payload: dict[str, object] = {
        "template": "stock_sector_rotation",
        "field_name": field_name,
        "reason": reason,
        "actual_value": actual_value,
    }
    payload.update(details)
    raise StrategySpecError(message, details=payload)


# ---------------------------------------------------------------------------
# StockSectorRotationConfig
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StockSectorRotationConfig:
    """
    stock_sector_rotation 策略模板的运行时配置.

    Attributes:
        sector_signal: 行业信号列名（从 signal_values DataFrame 中读取）。
        stock_signal: 个股信号列名（行业内选股排序用）。
        top_sectors: 选取排名前 K 的行业。
        stocks_per_sector: 每个行业内选取排名前 K 的个股。
        sector_weight_method: 行业间权重分配方式 (``"equal_weight"``)。
        stock_weight_method: 行业内权重分配方式 (``"equal_weight"``)。
        max_weight: 单标的最大权重。
        cash_target: 目标现金比例。
        rebalance_freq: 调仓频率 (``"daily"`` / ``"weekly"`` / ``"monthly"``)。
        regime_config: Regime 评分配置（None = 不使用 regime 缩放）。

    """

    sector_signal: str = "signal_value"
    stock_signal: str = "signal_value"
    top_sectors: int = 3
    stocks_per_sector: int = 3
    sector_weight_method: str = "equal_weight"
    stock_weight_method: str = "equal_weight"
    max_weight: float = 0.15
    cash_target: float = 0.0
    rebalance_freq: str = "daily"
    regime_config: RegimeConfig | None = None


# ---------------------------------------------------------------------------
# validate_config
# ---------------------------------------------------------------------------


def validate_config(config: StockSectorRotationConfig) -> None:
    """
    校验 StockSectorRotationConfig 合法性.

    Raises:
        StrategySpecError: 配置不合法时抛出描述性异常。

    """
    if config.top_sectors < 1:
        msg = f"top_sectors must be >= 1, got {config.top_sectors}"
        _raise_config_error(
            msg,
            field_name="top_sectors",
            reason="below_min",
            actual_value=config.top_sectors,
            min_value=1,
        )

    if config.stocks_per_sector < 1:
        msg = f"stocks_per_sector must be >= 1, got {config.stocks_per_sector}"
        _raise_config_error(
            msg,
            field_name="stocks_per_sector",
            reason="below_min",
            actual_value=config.stocks_per_sector,
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

    valid_weight_methods = ("equal_weight",)
    if config.sector_weight_method not in valid_weight_methods:
        msg = (
            f"sector_weight_method must be one of {valid_weight_methods}, "
            f"got '{config.sector_weight_method}'"
        )
        _raise_config_error(
            msg,
            field_name="sector_weight_method",
            reason="invalid_enum",
            actual_value=config.sector_weight_method,
            allowed_values=valid_weight_methods,
        )

    if config.stock_weight_method not in valid_weight_methods:
        msg = (
            f"stock_weight_method must be one of {valid_weight_methods}, "
            f"got '{config.stock_weight_method}'"
        )
        _raise_config_error(
            msg,
            field_name="stock_weight_method",
            reason="invalid_enum",
            actual_value=config.stock_weight_method,
            allowed_values=valid_weight_methods,
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


# ---------------------------------------------------------------------------
# get_param_constraints
# ---------------------------------------------------------------------------


def get_param_constraints() -> tuple[ParamConstraint, ...]:
    """
    返回 stock_sector_rotation 模板的参数扫描元数据.

    Returns:
        ParamConstraint 元组，描述可调参数的范围和可选值。

    """
    return (
        ParamConstraint(
            name="top_sectors",
            dtype="int",
            min_value=1,
            max_value=20,
            step=1,
        ),
        ParamConstraint(
            name="stocks_per_sector",
            dtype="int",
            min_value=1,
            max_value=20,
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
            name="cash_target",
            dtype="float",
            min_value=0.0,
            max_value=0.5,
            step=0.05,
        ),
        ParamConstraint(
            name="rebalance_freq",
            dtype="str",
            allowed_values=("daily", "weekly", "monthly"),
        ),
    )
