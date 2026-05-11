"""Spec JSON 反序列化函数 — 将 catalog 记录恢复为 StrategySpec 领域对象."""

from __future__ import annotations

from dataclasses import replace

from ditto_kernel.strategy import ImpactModel
from ditto_kernel.trading import DEFAULT_COMMISSION_RATE, DEFAULT_SLIPPAGE_BPS
from ditto_strategy.alpha.specs import (
    ConstraintSpec,
    CostModelSpec,
    ExecutionSpec,
    ParamConstraint,
    ScorerSpec,
    SelectorSpec,
    StrategySpec,
)
from ditto_strategy.alpha.templates import (
    get_param_constraints as get_stock_selection_param_constraints,
)
from ditto_strategy.alpha.templates import (
    get_sector_rotation_param_constraints,
)
from ditto_strategy.models import StrategySpecRecord

from ditto_application.builders._spec_deserializer import (
    as_float_tuple,
    as_object_dict,
    as_sequence,
    as_str_tuple,
    read_float,
    read_int,
    read_optional_float,
    read_optional_str,
    read_required_str,
)
from ditto_application.exceptions import AppBuilderError

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
    "deserialize_strategy_spec",
    "inject_template_constraints",
]

# ---------------------------------------------------------------------------
# Local defaults
# ---------------------------------------------------------------------------

_DEFAULT_SLIPPAGE_BPS = DEFAULT_SLIPPAGE_BPS
_DEFAULT_TRAILING_STOP_PCT = 0.08
_DEFAULT_MAX_WEIGHT = 0.15
_DEFAULT_TOP_K = 10


# ---------------------------------------------------------------------------
# Normalization helpers
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Top-level deserialization
# ---------------------------------------------------------------------------


def deserialize_strategy_spec(record: StrategySpecRecord) -> StrategySpec:
    """将 catalog 中的 ``spec_json`` 恢复为 ``StrategySpec``。"""
    payload = as_object_dict(record.spec_json, field_name="spec_json")
    spec = StrategySpec(
        strategy_id=read_optional_str(payload.get("strategy_id")) or record.strategy_id,
        name=read_optional_str(payload.get("name")) or record.name,
        template=read_required_str(payload, "template"),
        universe=read_required_str(payload, "universe"),
        asset_class=read_required_str(payload, "asset_class"),
        scorer=deserialize_scorer(payload.get("scorer")),
        selector=deserialize_selector(payload.get("selector")),
        execution=deserialize_execution(payload.get("execution")),
        constraints=deserialize_constraints(payload),
        benchmark=read_optional_str(payload.get("benchmark")),
        params=as_object_dict(payload.get("params"), field_name="params"),
        param_constraints=deserialize_param_constraints(payload),
        tags=as_str_tuple(payload.get("tags"), field_name="tags") or record.tags,
        signal_expressions=as_str_tuple(
            payload.get("signal_expressions"),
            field_name="signal_expressions",
        ),
        signal_weights=as_float_tuple(
            payload.get("signal_weights"),
            field_name="signal_weights",
        ),
    )
    return inject_template_constraints(spec)


# ---------------------------------------------------------------------------
# Component deserialization
# ---------------------------------------------------------------------------


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
    return ExecutionSpec(
        frequency=read_optional_str(payload.get("frequency")) or "M",
        method=read_optional_str(payload.get("method")) or "calendar",
        cost_model=deserialize_cost_model(payload.get("cost_model")),
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
) -> ParamConstraint:
    """恢复参数约束元数据。"""
    payload = as_object_dict(
        raw_value,
        field_name=f"param_constraints[{index}]",
    )
    return ParamConstraint(
        name=read_required_str(payload, "name"),
        dtype=read_required_str(payload, "dtype"),
        min_value=read_optional_float(
            payload.get("min_value"),
            field_name=f"param_constraints[{index}].min_value",
        ),
        max_value=read_optional_float(
            payload.get("max_value"),
            field_name=f"param_constraints[{index}].max_value",
        ),
        step=read_optional_float(
            payload.get("step"),
            field_name=f"param_constraints[{index}].step",
        ),
        allowed_values=as_str_tuple(
            payload.get("allowed_values"),
            field_name=f"param_constraints[{index}].allowed_values",
        ),
    )


# ---------------------------------------------------------------------------
# Template constraint injection
# ---------------------------------------------------------------------------


def inject_template_constraints(spec: StrategySpec) -> StrategySpec:
    """为模板型策略补齐缺失的参数约束元数据。"""
    if spec.param_constraints:
        return spec
    if spec.template == "stock_selection_trend":
        return replace(
            spec,
            param_constraints=get_stock_selection_param_constraints(),
        )
    if spec.template == "stock_sector_rotation":
        return replace(
            spec,
            param_constraints=get_sector_rotation_param_constraints(),
        )
    return spec
