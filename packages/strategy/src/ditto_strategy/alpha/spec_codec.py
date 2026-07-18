"""StrategySpec v2 canonical JSON codec 与显式 legacy migration adapter。"""

from __future__ import annotations

import hashlib
import math
from collections.abc import Mapping
from typing import TypeGuard

import orjson

from ditto_strategy.alpha.nodes import (
    NodeCategory,
    NodeInstance,
    NodeRef,
    PipelineSpec,
)
from ditto_strategy.alpha.specs import (
    STRATEGY_SPEC_V2_SCHEMA_VERSION,
    ParamConstraint,
    StrategyKind,
    StrategySpec,
    StrategySpecV2,
)
from ditto_strategy.errors import StrategySpecError

__all__ = [
    "adapt_legacy_strategy_spec",
    "canonical_spec_bytes",
    "canonical_spec_hash",
    "canonical_spec_payload",
]


def _codec_error(message: str, *, field_name: str, value: object) -> StrategySpecError:
    return StrategySpecError(
        message,
        details={
            "field_name": field_name,
            "reason": "non_canonical_value",
            "actual_type": type(value).__name__,
        },
    )


def _require_v2_spec(value: object) -> StrategySpecV2:
    if not isinstance(value, StrategySpecV2):
        raise StrategySpecError(
            "canonical spec codec only accepts StrategySpecV2",
            details={
                "field_name": "spec",
                "reason": "legacy_spec_not_allowed",
                "actual_type": type(value).__name__,
            },
        )
    return value


def _require_legacy_spec(value: object) -> StrategySpec:
    if not isinstance(value, StrategySpec):
        raise StrategySpecError(
            "legacy adapter only accepts legacy StrategySpec",
            details={
                "field_name": "spec",
                "reason": "invalid_legacy_spec",
                "actual_type": type(value).__name__,
            },
        )
    return value


def _is_object_mapping(value: object) -> TypeGuard[Mapping[object, object]]:
    return isinstance(value, Mapping)


def _is_object_sequence(
    value: object,
) -> TypeGuard[tuple[object, ...] | list[object]]:
    return isinstance(value, (tuple, list))


def _canonical_value(
    value: object,
    *,
    field_name: str,
) -> object:
    """把领域值收敛为 orjson 可稳定编码的 JSON value。"""
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise _codec_error(
                f"{field_name} has no canonical JSON identity",
                field_name=field_name,
                value=value,
            )
        return value
    if _is_object_mapping(value):
        result: dict[str, object] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise _codec_error(
                    f"{field_name} keys must be strings for canonical JSON",
                    field_name=field_name,
                    value=key,
                )
            result[key] = _canonical_value(
                item,
                field_name=f"{field_name}.{key}",
            )
        return result
    if _is_object_sequence(value):
        return [
            _canonical_value(item, field_name=f"{field_name}[{index}]")
            for index, item in enumerate(value)
        ]
    raise _codec_error(
        f"{field_name} has no canonical JSON identity",
        field_name=field_name,
        value=value,
    )


def _parameter_payload(
    parameter: ParamConstraint,
    numeric_identity: tuple[float | None, float | None, float | None],
) -> dict[str, object]:
    min_value, max_value, step = numeric_identity
    return {
        "allowed_values": list(parameter.allowed_values),
        "dtype": parameter.dtype,
        "max_value": _canonical_value(
            max_value,
            field_name=f"parameter_schema.{parameter.name}.max_value",
        ),
        "min_value": _canonical_value(
            min_value,
            field_name=f"parameter_schema.{parameter.name}.min_value",
        ),
        "name": parameter.name,
        "step": _canonical_value(
            step,
            field_name=f"parameter_schema.{parameter.name}.step",
        ),
    }


def canonical_spec_payload(spec: StrategySpecV2) -> dict[str, object]:
    """生成只包含执行身份字段的 canonical payload。"""
    spec = _require_v2_spec(spec)
    nodes_by_id = {node.node_id: node for node in spec.pipeline.nodes}
    ordered_nodes = tuple(nodes_by_id[node_id] for node_id in spec.pipeline.sequence)
    node_payloads = [
        {
            "category": node.category.value,
            "config": _canonical_value(
                node.config,
                field_name=f"pipeline.nodes.{node.node_id}.config",
            ),
            "enabled": node.enabled,
            "node_id": node.node_id,
            "node_type": node.ref.node_type,
            "node_version": node.ref.version,
        }
        for node in ordered_nodes
    ]
    validated_parameters = [
        (parameter, parameter.validate_canonical_identity())
        for parameter in spec.parameter_schema
    ]
    parameter_payloads = [
        _parameter_payload(parameter, numeric_identity)
        for parameter, numeric_identity in sorted(
            validated_parameters,
            key=lambda item: item[0].name,
        )
    ]
    return {
        "parameter_schema": parameter_payloads,
        "pipeline": {
            "nodes": node_payloads,
            "sequence": list(spec.pipeline.sequence),
        },
        "schema_version": spec.schema_version,
        "strategy_family_id": spec.strategy_family_id,
        "strategy_kind": spec.strategy_kind.value,
    }


def canonical_spec_bytes(spec: StrategySpecV2) -> bytes:
    """返回 recursive key-sorted、无缩进的 canonical JSON bytes。"""
    try:
        return orjson.dumps(
            canonical_spec_payload(spec),
            option=orjson.OPT_SORT_KEYS,
        )
    except (TypeError, ValueError, OverflowError) as exc:
        raise _codec_error(
            "spec has no canonical JSON identity",
            field_name="spec",
            value=spec,
        ) from exc


def canonical_spec_hash(spec: StrategySpecV2) -> str:
    """返回 canonical StrategySpec v2 的完整 64 位 SHA-256。"""
    return hashlib.sha256(canonical_spec_bytes(spec)).hexdigest()


def adapt_legacy_strategy_spec(spec: StrategySpec) -> StrategySpecV2:
    """把一个已验证 legacy spec 显式迁移为可哈希的 V2 值对象。"""
    spec = _require_legacy_spec(spec)
    effective_signal_weights = spec.signal_weights or (1.0,) * len(
        spec.signal_expressions
    )
    strategy_kind = (
        StrategyKind.STOCK_SELECTION
        if spec.template in {"stock_selection", "stock_sector_rotation"}
        else StrategyKind.ETF_ROTATION
    )
    nodes = (
        NodeInstance(
            node_id="legacy_universe",
            ref=NodeRef("legacy.universe", "1"),
            category=NodeCategory.UNIVERSE,
            config={
                "asset_class": spec.asset_class,
                "benchmark": spec.benchmark,
                "universe": spec.universe,
            },
        ),
        NodeInstance(
            node_id="legacy_factor_set",
            ref=NodeRef("legacy.factor_set", "1"),
            category=NodeCategory.FACTOR_SET,
            config={
                "params": spec.params,
                "required_datasets": spec.required_datasets,
                "signal_expressions": spec.signal_expressions,
                "signal_weights": effective_signal_weights,
                "template": spec.template,
            },
        ),
        NodeInstance(
            node_id="legacy_scorer",
            ref=NodeRef("legacy.scorer", "1"),
            category=NodeCategory.SCORER,
            config={
                "method": spec.scorer.method,
                "params": spec.scorer.params,
            },
        ),
        NodeInstance(
            node_id="legacy_selector",
            ref=NodeRef("legacy.selector", "1"),
            category=NodeCategory.SELECTOR,
            config={
                "method": spec.selector.method,
                "params": spec.selector.params,
            },
        ),
        NodeInstance(
            node_id="legacy_allocator",
            ref=NodeRef("legacy.allocator", "1"),
            category=NodeCategory.ALLOCATOR,
            config={
                "constraints": tuple(
                    {
                        "params": constraint.params,
                        "priority": constraint.priority,
                        "type": constraint.type,
                    }
                    for constraint in spec.constraints
                ),
            },
        ),
        NodeInstance(
            node_id="legacy_execution",
            ref=NodeRef("legacy.execution_assumption", "1"),
            category=NodeCategory.EXECUTION_ASSUMPTION,
            config={
                "cost_model": {
                    "commission_rate": (spec.execution.cost_model.commission_rate),
                    "impact_model": spec.execution.cost_model.impact_model,
                    "slippage_bps": spec.execution.cost_model.slippage_bps,
                },
                "default_order_type": spec.execution.default_order_type,
                "frequency": spec.execution.frequency,
                "method": spec.execution.method,
            },
        ),
        NodeInstance(
            node_id="legacy_validation",
            ref=NodeRef("legacy.validation", "1"),
            category=NodeCategory.VALIDATION,
            config={"legacy_contract": "strategy_spec_v1"},
        ),
    )
    return StrategySpecV2(
        schema_version=STRATEGY_SPEC_V2_SCHEMA_VERSION,
        strategy_family_id=spec.strategy_id,
        strategy_kind=strategy_kind,
        name=spec.name,
        pipeline=PipelineSpec(
            nodes=nodes,
            sequence=tuple(node.node_id for node in nodes),
        ),
        parameter_schema=tuple(spec.param_constraints),
        metadata={
            "legacy_strategy_id": spec.strategy_id,
            "migration_source": "legacy_strategy_spec",
        },
        tags=tuple(spec.tags),
    )
