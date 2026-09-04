"""Shared catalog JSON to StrategySpec deserialization boundary."""

from __future__ import annotations

import warnings
from collections.abc import Mapping
from dataclasses import replace
from typing import cast

from ditto_kernel.order import OrderType
from ditto_kernel.strategy import ImpactModel
from ditto_kernel.trading import DEFAULT_COMMISSION_RATE, DEFAULT_SLIPPAGE_BPS
from ditto_platform.foundation.json_types import JsonValue
from ditto_strategy.alpha.nodes import (
    NodeCategory,
    NodeInstance,
    NodeRef,
    PipelineSpec,
)
from ditto_strategy.alpha.spec_codec import (
    adapt_legacy_strategy_spec,
    canonical_spec_hash,
    canonical_spec_payload,
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
    ETFRotationConfig,
    ETFTrendSwingConfig,
    StockSelectionTrendConfig,
    get_etf_rotation_param_constraints,
    get_etf_trend_swing_param_constraints,
    get_sector_rotation_param_constraints,
)
from ditto_strategy.alpha.templates import (
    get_param_constraints as get_stock_selection_param_constraints,
)
from ditto_strategy.errors import StrategySpecError
from ditto_strategy.models import StrategySpecRecord

from ditto_application.contracts import SpecChange
from ditto_application.exceptions import AppBuilderError
from ditto_application.strategy_spec_fields import (
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

__all__ = [
    "_DEFAULT_MAX_WEIGHT",
    "_DEFAULT_SLIPPAGE_BPS",
    "_DEFAULT_TOP_K",
    "_DEFAULT_TRAILING_STOP_PCT",
    "_normalize_impact_model",
    "canonical_spec_hash_for_record",
    "canonical_spec_payload_for_record",
    "default_required_datasets_for_template",
    "deserialize_constraint",
    "deserialize_constraints",
    "deserialize_cost_model",
    "deserialize_execution",
    "deserialize_param_constraint",
    "deserialize_param_constraints",
    "deserialize_persisted_legacy_strategy_spec",
    "deserialize_scorer",
    "deserialize_selector",
    "deserialize_strategy_spec",
    "deserialize_strategy_spec_v2",
    "diff_canonical_payloads",
    "inject_template_constraints",
    "resolve_rebalance_frequency",
]

# ---------------------------------------------------------------------------
# Local defaults
# ---------------------------------------------------------------------------

_DEFAULT_SLIPPAGE_BPS = DEFAULT_SLIPPAGE_BPS
_DEFAULT_TRAILING_STOP_PCT = 0.08
_DEFAULT_MAX_WEIGHT = 0.15
_DEFAULT_TOP_K = 10


def resolve_rebalance_frequency(frequency: str) -> str:
    """Map persisted execution frequency to the template's effective value."""
    return {
        "D": "daily",
        "W": "weekly",
        "M": "monthly",
    }.get(frequency, "daily")


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


# ---------------------------------------------------------------------------
# Top-level deserialization
# ---------------------------------------------------------------------------


def _legacy_parameter_constraints(
    template: str,
    declared: tuple[ParamConstraint, ...],
) -> tuple[ParamConstraint, ...]:
    if declared:
        return declared
    if template == "etf_rotation":
        return get_etf_rotation_param_constraints()
    if template == "etf_trend_swing":
        return get_etf_trend_swing_param_constraints()
    if template == "stock_selection":
        return get_stock_selection_param_constraints()
    if template == "stock_sector_rotation":
        return get_sector_rotation_param_constraints()
    return ()


def _normalize_legacy_parameter_numbers(
    params: dict[str, object],
    *,
    template: str,
    constraints: tuple[ParamConstraint, ...],
) -> dict[str, object]:
    """Restore declared float values after a JavaScript JSON round trip."""
    normalized = dict(params)
    for constraint in _legacy_parameter_constraints(template, constraints):
        value = normalized.get(constraint.name)
        if constraint.dtype == "float" and type(value) is int:
            normalized[constraint.name] = read_float(
                value,
                field_name=f"params.{constraint.name}",
            )
    return normalized


def deserialize_persisted_legacy_strategy_spec(
    record: StrategySpecRecord,
) -> StrategySpec:
    """Decode the legacy shape without injecting fields or defaults."""
    payload = as_object_dict(record.spec_json, field_name="spec_json")
    template = read_required_str(payload, "template")
    param_constraints = deserialize_param_constraints(payload)
    params = _normalize_legacy_parameter_numbers(
        as_object_dict(payload.get("params"), field_name="params"),
        template=template,
        constraints=param_constraints,
    )
    required_datasets = as_str_tuple(
        payload.get("required_datasets"),
        field_name="required_datasets",
    )
    if not required_datasets:
        message = f"Strategy {record.strategy_id} missing required_datasets"
        message += "; using template migration default"
        warnings.warn(message, stacklevel=2)
        required_datasets = default_required_datasets_for_template(template)
    return StrategySpec(
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
        params=params,
        param_constraints=param_constraints,
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


def deserialize_strategy_spec(record: StrategySpecRecord) -> StrategySpec:
    """将 catalog 中的 ``spec_json`` 恢复为 ``StrategySpec``。"""
    return inject_template_constraints(
        deserialize_persisted_legacy_strategy_spec(record)
    )


def canonical_spec_payload_for_record(record: StrategySpecRecord) -> dict[str, object]:
    """
    计算 ``record.spec_json`` 的 canonical V2 payload.

    走 legacy deserialize → V2 adapt → ``canonical_spec_payload``，与
    ``canonical_spec_hash_for_record`` 同源，供 spec diff 复用同一规范化形态。
    """
    spec = deserialize_strategy_spec(record)
    v2 = adapt_legacy_strategy_spec(spec)
    return canonical_spec_payload(v2)


def canonical_spec_hash_for_record(record: StrategySpecRecord) -> str:
    """
    计算 ``record.spec_json`` 的 canonical V2 hash.

    委托 ``canonical_spec_hash``（与 ``canonical_spec_payload_for_record`` 共享
    同一 V2 payload 来源），与 backtest manifest 的 spec_hash 同源，保证
    governance 版本与回测版本内容寻址一致。
    """
    return canonical_spec_hash(
        adapt_legacy_strategy_spec(deserialize_strategy_spec(record))
    )


def diff_canonical_payloads(
    base: dict[str, object],
    target: dict[str, object],
) -> tuple[SpecChange, ...]:
    """
    递归比较两个 canonical spec payload，返回字段级变更.

    dict 按 key（sorted）遍历，list 按 index 对齐；非 dict/list leaf 用相等
    判定。type 不匹配（如 dict vs scalar）整体记为 ``changed``，不递归。
    """
    changes: list[SpecChange] = []
    _collect_payload_changes(
        "",
        cast("JsonValue", base),
        cast("JsonValue", target),
        changes,
    )
    return tuple(changes)


_KEYED_LIST_FIELDS: Mapping[str, str] = {
    "parameter_schema": "name",
    "pipeline.nodes": "node_id",
}


def _collect_payload_changes(
    prefix: str,
    base: JsonValue,
    target: JsonValue,
    changes: list[SpecChange],
) -> None:
    if isinstance(base, dict) and isinstance(target, dict):
        for key in sorted(set(base) | set(target), key=str):
            path = f"{prefix}.{key}" if prefix else str(key)
            if key not in base:
                changes.append(
                    SpecChange(
                        path=path,
                        op="added",
                        old_value=None,
                        new_value=target[key],
                    ),
                )
            elif key not in target:
                changes.append(
                    SpecChange(
                        path=path,
                        op="removed",
                        old_value=base[key],
                        new_value=None,
                    ),
                )
            else:
                _collect_payload_changes(path, base[key], target[key], changes)
    elif isinstance(base, list) and isinstance(target, list):
        key_field = _KEYED_LIST_FIELDS.get(prefix)
        if key_field is None:
            _collect_indexed_list(prefix, base, target, changes)
        else:
            _collect_keyed_list(prefix, key_field, base, target, changes)
    elif base != target:
        changes.append(
            SpecChange(path=prefix, op="changed", old_value=base, new_value=target),
        )


def _collect_indexed_list(
    prefix: str,
    base: list[JsonValue],
    target: list[JsonValue],
    changes: list[SpecChange],
) -> None:
    for index in range(max(len(base), len(target))):
        path = f"{prefix}[{index}]"
        if index >= len(base):
            changes.append(
                SpecChange(
                    path=path,
                    op="added",
                    old_value=None,
                    new_value=target[index],
                ),
            )
        elif index >= len(target):
            changes.append(
                SpecChange(
                    path=path,
                    op="removed",
                    old_value=base[index],
                    new_value=None,
                ),
            )
        else:
            _collect_payload_changes(path, base[index], target[index], changes)


def _collect_keyed_list(
    prefix: str,
    key_field: str,
    base: list[JsonValue],
    target: list[JsonValue],
    changes: list[SpecChange],
) -> None:
    """
    对按键字段定位身份的 list（parameter_schema/pipeline.nodes）按键 diff.

    避免 index 对齐在中间插入/删除时级联假变更——按 name/node_id 匹配元素身份。
    """
    base_map = {_list_key(item, key_field): item for item in base}
    target_map = {_list_key(item, key_field): item for item in target}
    for key in sorted(set(base_map) | set(target_map), key=str):
        path = f"{prefix}[{key}]"
        if key not in base_map:
            changes.append(
                SpecChange(
                    path=path,
                    op="added",
                    old_value=None,
                    new_value=target_map[key],
                ),
            )
        elif key not in target_map:
            changes.append(
                SpecChange(
                    path=path,
                    op="removed",
                    old_value=base_map[key],
                    new_value=None,
                ),
            )
        else:
            _collect_payload_changes(path, base_map[key], target_map[key], changes)


def _list_key(item: JsonValue, key_field: str) -> str:
    if isinstance(item, dict):
        value = item.get(key_field)
        return value if isinstance(value, str) else ""
    return ""


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


# ---------------------------------------------------------------------------
# Template constraint injection
# ---------------------------------------------------------------------------


def inject_template_constraints(spec: StrategySpec) -> StrategySpec:
    """为模板型策略补齐缺失的参数约束元数据。"""
    if spec.param_constraints:
        return spec
    if spec.template == "etf_rotation":
        defaults = ETFRotationConfig()
        selector_k = spec.selector.params.get("k")
        return replace(
            spec,
            params={
                "allocation_method": defaults.allocation_method,
                "cash_target": defaults.cash_target,
                "top_k": defaults.top_k if selector_k is None else selector_k,
                **spec.params,
            },
            param_constraints=get_etf_rotation_param_constraints(),
        )
    if spec.template == "etf_trend_swing":
        defaults = ETFTrendSwingConfig()
        selector_k = spec.selector.params.get("k")
        return replace(
            spec,
            params={
                "allocation_method": defaults.allocation_method,
                "cash_target": defaults.cash_target,
                "lookback_window": defaults.lookback_window,
                "max_positions": (
                    defaults.max_positions if selector_k is None else selector_k
                ),
                "trailing_stop_pct": defaults.trailing_stop_pct,
                "trend_threshold": defaults.trend_threshold,
                **spec.params,
            },
            param_constraints=get_etf_trend_swing_param_constraints(),
        )
    if spec.template == "stock_selection":
        defaults = StockSelectionTrendConfig()
        selector_k = spec.selector.params.get("k")
        return replace(
            spec,
            params={
                "allocation_method": defaults.allocation_method,
                "cash_target": defaults.cash_target,
                "max_weight": defaults.max_weight,
                "rebalance_freq": resolve_rebalance_frequency(
                    spec.execution.frequency,
                ),
                "top_k": defaults.top_k if selector_k is None else selector_k,
                "trend_threshold": defaults.trend_threshold,
                **spec.params,
            },
            param_constraints=get_stock_selection_param_constraints(),
        )
    if spec.template == "stock_sector_rotation":
        return replace(
            spec,
            param_constraints=get_sector_rotation_param_constraints(),
        )
    return spec
