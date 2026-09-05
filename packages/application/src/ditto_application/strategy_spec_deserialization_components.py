"""Shared component decoders for persisted strategy specifications."""

from __future__ import annotations

from ditto_kernel.order import OrderType
from ditto_kernel.strategy import ImpactModel
from ditto_kernel.trading import DEFAULT_COMMISSION_RATE, DEFAULT_SLIPPAGE_BPS
from ditto_strategy.alpha.specs import (
    ConstraintSpec,
    CostModelSpec,
    ExecutionSpec,
    ParamConstraint,
    ScorerSpec,
    SelectorSpec,
)

from ditto_application.exceptions import AppBuilderError
from ditto_application.strategy_spec_fields import (
    as_object_dict,
    as_sequence,
    as_str_tuple,
    read_float,
    read_int,
    read_optional_float,
    read_optional_str,
    read_required_str,
)

__all__ = [
    "_DEFAULT_MAX_WEIGHT",
    "_DEFAULT_SLIPPAGE_BPS",
    "_DEFAULT_TOP_K",
    "_DEFAULT_TRAILING_STOP_PCT",
    "_normalize_impact_model",
    "deserialize_constraint",
    "deserialize_constraints",
    "deserialize_cost_model",
    "deserialize_execution",
    "deserialize_param_constraint",
    "deserialize_param_constraints",
    "deserialize_scorer",
    "deserialize_selector",
]

_DEFAULT_SLIPPAGE_BPS = DEFAULT_SLIPPAGE_BPS
_DEFAULT_TRAILING_STOP_PCT = 0.08
_DEFAULT_MAX_WEIGHT = 0.15
_DEFAULT_TOP_K = 10


def _normalize_impact_model(raw: str | None) -> ImpactModel:
    """
    将 impact_model 字符串规范化为 ImpactModel 合法值.

    Raises:
        ValueError: raw 不为 None 且不是合法值时抛出.

    """
    if raw is None:
        return ImpactModel.NONE
    if raw in (ImpactModel.NONE, ImpactModel.VOLUME_SHARE):
        return ImpactModel(raw)
    msg = f"非法 impact_model 值: {raw!r}, 合法值: 'none', 'volume_share'"
    raise AppBuilderError(msg)


def _normalize_order_type(raw: str | None) -> OrderType:
    """严格恢复持久化订单类型；只有缺失字段由调用方采用迁移默认。"""
    if raw is None:
        msg = "execution.default_order_type 必须是非空 OrderType 值"
        raise AppBuilderError(msg)
    try:
        return OrderType(raw)
    except ValueError as exc:
        valid = ", ".join(repr(value.value) for value in OrderType)
        msg = f"execution.default_order_type 不受支持: {raw!r}; 合法值: {valid}"
        raise AppBuilderError(msg) from exc


def deserialize_constraints(
    payload: dict[str, object],
) -> tuple[ConstraintSpec, ...]:
    """从 payload 中反序列化约束列表。"""
    raw_items = as_sequence(
        payload.get("constraints"),
        field_name="constraints",
    )
    return tuple(
        deserialize_constraint(item, index=index)
        for index, item in enumerate(raw_items)
    )


def deserialize_param_constraints(
    payload: dict[str, object],
) -> tuple[ParamConstraint, ...]:
    """从 payload 中反序列化参数约束列表。"""
    raw_items = as_sequence(
        payload.get("param_constraints"),
        field_name="param_constraints",
    )
    return tuple(
        deserialize_param_constraint(item, index=index)
        for index, item in enumerate(raw_items)
    )


def deserialize_scorer(raw_value: object) -> ScorerSpec:
    """恢复评分器配置。"""
    payload = as_object_dict(raw_value, field_name="scorer")
    return ScorerSpec(
        method=read_optional_str(payload.get("method")) or "equal_weight",
        params=as_object_dict(
            payload.get("params"),
            field_name="scorer.params",
        ),
    )


def deserialize_selector(raw_value: object) -> SelectorSpec:
    """恢复选择器配置。"""
    payload = as_object_dict(raw_value, field_name="selector")
    return SelectorSpec(
        method=read_optional_str(payload.get("method")) or "top_k",
        params=as_object_dict(
            payload.get("params"),
            field_name="selector.params",
        ),
    )


def deserialize_execution(raw_value: object) -> ExecutionSpec:
    """恢复执行层配置。"""
    payload = as_object_dict(raw_value, field_name="execution")
    default_order_type = OrderType.MARKET
    if "default_order_type" in payload:
        default_order_type = _normalize_order_type(
            read_optional_str(
                payload.get("default_order_type"),
                field_name="execution.default_order_type",
            ),
        )
    return ExecutionSpec(
        frequency=read_optional_str(payload.get("frequency")) or "M",
        method=read_optional_str(payload.get("method")) or "calendar",
        cost_model=deserialize_cost_model(payload.get("cost_model")),
        default_order_type=default_order_type,
    )


def deserialize_cost_model(raw_value: object) -> CostModelSpec:
    """恢复成本模型配置。"""
    payload = as_object_dict(raw_value, field_name="execution.cost_model")
    return CostModelSpec(
        commission_rate=read_float(
            payload.get("commission_rate", DEFAULT_COMMISSION_RATE),
            field_name="execution.cost_model.commission_rate",
        ),
        slippage_bps=read_float(
            payload.get("slippage_bps", _DEFAULT_SLIPPAGE_BPS),
            field_name="execution.cost_model.slippage_bps",
        ),
        impact_model=_normalize_impact_model(
            read_optional_str(payload.get("impact_model")),
        ),
    )


def deserialize_constraint(
    raw_value: object,
    *,
    index: int,
) -> ConstraintSpec:
    """恢复单条约束配置。"""
    payload = as_object_dict(raw_value, field_name=f"constraints[{index}]")
    return ConstraintSpec(
        type=read_required_str(payload, "type"),
        params=as_object_dict(
            payload.get("params"),
            field_name=f"constraints[{index}].params",
        ),
        priority=read_int(
            payload.get("priority", 100),
            field_name=f"constraints[{index}].priority",
        ),
    )


def deserialize_param_constraint(
    raw_value: object,
    *,
    index: int,
    collection_field_name: str = "param_constraints",
) -> ParamConstraint:
    """恢复参数约束元数据。"""
    item_field_name = f"{collection_field_name}[{index}]"
    payload = as_object_dict(
        raw_value,
        field_name=item_field_name,
    )
    return ParamConstraint(
        name=read_required_str(payload, "name"),
        dtype=read_required_str(payload, "dtype"),
        min_value=read_optional_float(
            payload.get("min_value"),
            field_name=f"{item_field_name}.min_value",
        ),
        max_value=read_optional_float(
            payload.get("max_value"),
            field_name=f"{item_field_name}.max_value",
        ),
        step=read_optional_float(
            payload.get("step"),
            field_name=f"{item_field_name}.step",
        ),
        allowed_values=as_str_tuple(
            payload.get("allowed_values"),
            field_name=f"{item_field_name}.allowed_values",
        ),
    )
