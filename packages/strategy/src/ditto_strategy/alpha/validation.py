"""
StrategySpec 参数校验 — 独立验证函数。

根据 param_constraints 定义校验 params 字典，
对不合法参数抛出 StrategySpecError，对合法参数静默通过。
"""

from __future__ import annotations

from typing import NoReturn

from ditto_strategy.alpha.specs import ParamConstraint, StrategySpec
from ditto_strategy.errors import StrategySpecError

__all__ = ["validate_spec_params"]


def validate_spec_params(spec: StrategySpec) -> None:
    """
    校验 spec.params 是否满足 spec.param_constraints 约束。

    检查项：
    - 必填参数是否存在（param_constraints 中定义的参数）
    - 参数值类型是否匹配 dtype
    - 数值型参数是否在 min_value / max_value 范围内
    - 枚举型参数是否在 allowed_values 内

    Args:
        spec: 策略定义对象

    Raises:
        StrategySpecError: 参数不满足约束时抛出，包含描述性错误信息

    """
    params = spec.params

    for constraint in spec.param_constraints:
        name = constraint.name

        if name not in params:
            _raise_spec_error(
                f"缺少必填参数: {name}",
                spec_name=spec.name,
                param_name=name,
                reason="missing_param",
            )

        value = params[name]
        _validate_single_constraint(spec.name, name, value, constraint)


def _raise_spec_error(
    message: str,
    *,
    spec_name: str,
    param_name: str,
    reason: str,
    **details: object,
) -> NoReturn:
    """Build a StrategySpecError with consistent boundary details."""
    payload: dict[str, object] = {
        "spec_name": spec_name,
        "param_name": param_name,
        "reason": reason,
    }
    payload.update(details)
    raise StrategySpecError(message, details=payload)


def _validate_single_constraint(
    spec_name: str,
    name: str,
    value: object,
    constraint: ParamConstraint,
) -> None:
    """校验单个参数约束，不合法时抛出 StrategySpecError。"""
    dtype = constraint.dtype

    if dtype in ("int", "float"):
        expected = int if dtype == "int" else (int, float)
        if not isinstance(value, expected) or isinstance(value, bool):
            actual_type = type(value).__name__
            _raise_spec_error(
                f"参数 {name} 类型错误: 期望 {dtype}, 实际 {actual_type}",
                spec_name=spec_name,
                param_name=name,
                reason="wrong_type",
                expected_dtype=dtype,
                actual_type=actual_type,
            )
        _check_numeric_range(spec_name, name, float(value), constraint)
        return

    if dtype == "str":
        if not isinstance(value, str):
            actual_type = type(value).__name__
            _raise_spec_error(
                f"参数 {name} 类型错误: 期望 str, 实际 {actual_type}",
                spec_name=spec_name,
                param_name=name,
                reason="wrong_type",
                expected_dtype="str",
                actual_type=actual_type,
            )
        if constraint.allowed_values and value not in constraint.allowed_values:
            allowed = list(constraint.allowed_values)
            _raise_spec_error(
                f"参数 {name} 值无效: '{value}' 不在允许值 {allowed} 中",
                spec_name=spec_name,
                param_name=name,
                reason="invalid_enum",
                allowed_values=allowed,
                actual_value=value,
            )
        return

    _raise_spec_error(
        f"参数 {name} 类型约束不支持: {dtype}",
        spec_name=spec_name,
        param_name=name,
        reason="unsupported_dtype",
        expected_dtype=dtype,
    )


def _check_numeric_range(
    spec_name: str,
    name: str,
    value: float,
    constraint: ParamConstraint,
) -> None:
    """检查数值型参数的范围约束，越界时抛出 StrategySpecError。"""
    if constraint.min_value is not None and value < constraint.min_value:
        _raise_spec_error(
            f"参数 {name} 值 {value} 小于最小值 {constraint.min_value}",
            spec_name=spec_name,
            param_name=name,
            reason="below_min",
            min_value=constraint.min_value,
            actual_value=value,
        )
    if constraint.max_value is not None and value > constraint.max_value:
        _raise_spec_error(
            f"参数 {name} 值 {value} 大于最大值 {constraint.max_value}",
            spec_name=spec_name,
            param_name=name,
            reason="above_max",
            max_value=constraint.max_value,
            actual_value=value,
        )
