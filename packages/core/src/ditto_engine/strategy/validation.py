"""
StrategySpec 参数校验 — 独立验证函数。

根据 param_constraints 定义校验 params 字典，
返回错误信息列表（空列表表示校验通过）。
"""

from __future__ import annotations

from ditto_engine.strategy.specs import ParamConstraint, StrategySpec

__all__ = ["validate_spec_params"]


def validate_spec_params(spec: StrategySpec) -> list[str]:
    """
    校验 spec.params 是否满足 spec.param_constraints 约束。

    检查项：
    - 必填参数是否存在（param_constraints 中定义的参数）
    - 参数值类型是否匹配 dtype
    - 数值型参数是否在 min_value / max_value 范围内
    - 枚举型参数是否在 allowed_values 内

    Args:
        spec: 策略定义对象

    Returns:
        错误信息列表，空列表表示校验通过

    """
    errors: list[str] = []
    params = spec.params

    for constraint in spec.param_constraints:
        name = constraint.name

        # 检查必填参数
        if name not in params:
            errors.append(f"缺少必填参数: {name}")
            continue

        value = params[name]

        # 类型校验
        if constraint.dtype == "int":
            if not isinstance(value, int) or isinstance(value, bool):
                errors.append(
                    f"参数 {name} 类型错误: 期望 int, 实际 {type(value).__name__}"
                )
                continue
            _check_numeric_range(name, float(value), constraint, errors)
        elif constraint.dtype == "float":
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                errors.append(
                    f"参数 {name} 类型错误: 期望 float, 实际 {type(value).__name__}"
                )
                continue
            _check_numeric_range(name, float(value), constraint, errors)
        elif constraint.dtype == "str":
            if not isinstance(value, str):
                errors.append(
                    f"参数 {name} 类型错误: 期望 str, 实际 {type(value).__name__}"
                )
                continue
            # 枚举值校验
            if constraint.allowed_values and value not in constraint.allowed_values:
                allowed = list(constraint.allowed_values)
                errors.append(f"参数 {name} 值无效: '{value}' 不在允许值 {allowed} 中")

    return errors


def _check_numeric_range(
    name: str,
    value: float,
    constraint: ParamConstraint,
    errors: list[str],
) -> None:
    """检查数值型参数的范围约束。"""
    if constraint.min_value is not None and value < constraint.min_value:
        errors.append(f"参数 {name} 值 {value} 小于最小值 {constraint.min_value}")
    if constraint.max_value is not None and value > constraint.max_value:
        errors.append(f"参数 {name} 值 {value} 大于最大值 {constraint.max_value}")
