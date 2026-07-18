"""Spec JSON 反序列化函数 — 将 catalog 记录恢复为 StrategySpec 领域对象."""

from __future__ import annotations

import warnings
from dataclasses import replace

from ditto_kernel.strategy import ImpactModel
from ditto_kernel.trading import DEFAULT_COMMISSION_RATE, DEFAULT_SLIPPAGE_BPS
from ditto_strategy.alpha.nodes import (
    NodeCategory,
    NodeInstance,
    NodeRef,
    PipelineSpec,
)
from ditto_strategy.alpha.specs import (
    STRATEGY_SPEC_V2_SCHEMA_VERSION,
    ConstraintSpec,
    CostModelSpec,
    ExecutionSpec,
    ParamConstraint,
    ScorerSpec,
    SelectorSpec,
    StrategyKind,
    StrategySpec,
    StrategySpecV2,
)
from ditto_strategy.alpha.templates import (
    get_param_constraints as get_stock_selection_param_constraints,
)
from ditto_strategy.alpha.templates import (
    get_sector_rotation_param_constraints,
)
from ditto_strategy.errors import StrategySpecError
from ditto_strategy.models import StrategySpecRecord

from ditto_application.builders._spec_deserializer import (
    as_float_tuple,
    as_object_dict,
    as_sequence,
    as_str_tuple,
    read_bool,
    read_float,
    read_int,
    read_optional_float,
    read_optional_str,
    read_required_str,
    read_required_value,
)
from ditto_application.exceptions import AppBuilderError

__all__ = [
    "_DEFAULT_MAX_WEIGHT",
    "_DEFAULT_SLIPPAGE_BPS",
    "_DEFAULT_TOP_K",
    "_DEFAULT_TRAILING_STOP_PCT",
    "_normalize_impact_model",
    "default_required_datasets_for_template",
    "deserialize_constraint",
    "deserialize_constraints",
    "deserialize_cost_model",
    "deserialize_execution",
    "deserialize_param_constraint",
    "deserialize_param_constraints",
    "deserialize_scorer",
    "deserialize_selector",
    "deserialize_strategy_spec",
    "deserialize_strategy_spec_v2",
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
    template = read_required_str(payload, "template")
    required_datasets = as_str_tuple(
        payload.get("required_datasets"),
        field_name="required_datasets",
    )
    if not required_datasets:
        message = f"Strategy {record.strategy_id} missing required_datasets"
        message += "; using template migration default"
        warnings.warn(message, stacklevel=2)
        required_datasets = default_required_datasets_for_template(template)
    spec = StrategySpec(
        strategy_id=read_optional_str(payload.get("strategy_id")) or record.strategy_id,
        name=read_optional_str(payload.get("name")) or record.name,
        template=template,
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
        required_datasets=required_datasets,
    )
    return inject_template_constraints(spec)


def deserialize_strategy_spec_v2(record: StrategySpecRecord) -> StrategySpecV2:
    """严格恢复 canonical V2；legacy payload 必须先走显式 migration adapter。"""
    payload = as_object_dict(record.spec_json, field_name="spec_json")
    _require_exact_fields(
        payload,
        field_name="spec_json",
        required={
            "schema_version",
            "strategy_family_id",
            "strategy_kind",
            "name",
            "pipeline",
            "parameter_schema",
            "metadata",
            "tags",
        },
        optional=set(),
    )
    schema_version = read_required_value(payload, "schema_version")
    if (
        not isinstance(schema_version, int)
        or isinstance(schema_version, bool)
        or schema_version != STRATEGY_SPEC_V2_SCHEMA_VERSION
    ):
        msg = f"spec_json.schema_version 必须严格等于 2, 实际值: {schema_version!r}"
        raise AppBuilderError(msg)

    strategy_kind_raw = read_required_str(payload, "strategy_kind")
    try:
        strategy_kind = StrategyKind(strategy_kind_raw)
    except ValueError as exc:
        msg = f"spec_json.strategy_kind 不受支持: {strategy_kind_raw!r}"
        raise AppBuilderError(msg) from exc

    parameter_schema_raw = _require_v2_non_null(
        read_required_value(payload, "parameter_schema"),
        field_name="parameter_schema",
    )
    metadata_raw = _require_v2_non_null(
        read_required_value(payload, "metadata"),
        field_name="metadata",
    )
    tags_raw = _require_v2_non_null(
        read_required_value(payload, "tags"),
        field_name="tags",
    )

    try:
        return StrategySpecV2(
            schema_version=schema_version,
            strategy_family_id=read_required_str(payload, "strategy_family_id"),
            strategy_kind=strategy_kind,
            name=read_required_str(payload, "name"),
            pipeline=_deserialize_pipeline_v2(
                read_required_value(payload, "pipeline"),
            ),
            parameter_schema=_deserialize_parameter_schema_v2(
                parameter_schema_raw,
            ),
            metadata=as_object_dict(
                metadata_raw,
                field_name="metadata",
            ),
            tags=as_str_tuple(
                tags_raw,
                field_name="tags",
            ),
        )
    except StrategySpecError as exc:
        raise AppBuilderError(str(exc), details=exc.details) from exc


def _deserialize_pipeline_v2(raw_value: object) -> PipelineSpec:
    payload = as_object_dict(raw_value, field_name="pipeline")
    _require_exact_fields(
        payload,
        field_name="pipeline",
        required={"nodes", "sequence"},
        optional=set(),
    )
    raw_nodes = as_sequence(
        _require_v2_non_null(
            read_required_value(payload, "nodes"),
            field_name="pipeline.nodes",
        ),
        field_name="pipeline.nodes",
    )
    nodes = tuple(
        _deserialize_node_v2(raw_node, index=index)
        for index, raw_node in enumerate(raw_nodes)
    )
    sequence = as_str_tuple(
        _require_v2_non_null(
            read_required_value(payload, "sequence"),
            field_name="pipeline.sequence",
        ),
        field_name="pipeline.sequence",
    )
    return PipelineSpec(nodes=nodes, sequence=sequence)


def _deserialize_node_v2(raw_value: object, *, index: int) -> NodeInstance:
    field_name = f"pipeline.nodes[{index}]"
    payload = as_object_dict(raw_value, field_name=field_name)
    _require_exact_fields(
        payload,
        field_name=field_name,
        required={
            "node_id",
            "node_type",
            "node_version",
            "category",
            "config",
            "enabled",
        },
        optional=set(),
    )
    category_raw = read_required_str(payload, "category")
    try:
        category = NodeCategory(category_raw)
    except ValueError as exc:
        msg = f"{field_name}.category 不受支持: {category_raw!r}"
        raise AppBuilderError(msg) from exc
    enabled = read_bool(
        read_required_value(payload, "enabled"),
        field_name=f"{field_name}.enabled",
    )
    config_raw = _require_v2_non_null(
        read_required_value(payload, "config"),
        field_name=f"{field_name}.config",
    )
    return NodeInstance(
        node_id=read_required_str(payload, "node_id"),
        ref=NodeRef(
            node_type=read_required_str(payload, "node_type"),
            version=read_required_str(payload, "node_version"),
        ),
        category=category,
        config=as_object_dict(
            config_raw,
            field_name=f"{field_name}.config",
        ),
        enabled=enabled,
    )


def _deserialize_parameter_schema_v2(
    raw_value: object,
) -> tuple[ParamConstraint, ...]:
    raw_items = as_sequence(raw_value, field_name="parameter_schema")
    parameters: list[ParamConstraint] = []
    for index, raw_item in enumerate(raw_items):
        field_name = f"parameter_schema[{index}]"
        payload = as_object_dict(raw_item, field_name=field_name)
        _require_exact_fields(
            payload,
            field_name=field_name,
            required={"name", "dtype"},
            optional={
                "min_value",
                "max_value",
                "step",
                "allowed_values",
            },
        )
        parameters.append(
            deserialize_param_constraint(
                payload,
                index=index,
                collection_field_name="parameter_schema",
            ),
        )
    return tuple(parameters)


def _require_exact_fields(
    payload: dict[str, object],
    *,
    field_name: str,
    required: set[str],
    optional: set[str],
) -> None:
    missing = sorted(required - payload.keys())
    unknown = sorted(payload.keys() - required - optional)
    if missing or unknown:
        msg = f"{field_name} 字段不符合 V2 contract"
        if missing:
            msg += f"; missing={missing}"
        if unknown:
            msg += f"; unknown={unknown}"
        raise AppBuilderError(msg)


def _require_v2_non_null(value: object, *, field_name: str) -> object:
    if value is None:
        msg = f"{field_name} 不能为 null"
        raise AppBuilderError(msg)
    return value


def default_required_datasets_for_template(template: str) -> tuple[str, ...]:
    """旧 spec 的兼容映射；新写入必须显式保存 required_datasets。"""
    if template in {"etf_rotation", "etf_trend_swing"}:
        return ("etf_daily",)
    if template == "stock_selection":
        return (
            "stock_daily",
            "adj_factor",
            "balance_sheet",
            "income_statement",
        )
    if template == "stock_sector_rotation":
        return ("stock_daily", "adj_factor")
    return ()


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


# ---------------------------------------------------------------------------
# Template constraint injection
# ---------------------------------------------------------------------------


def inject_template_constraints(spec: StrategySpec) -> StrategySpec:
    """为模板型策略补齐缺失的参数约束元数据。"""
    if spec.param_constraints:
        return spec
    if spec.template == "stock_selection":
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
