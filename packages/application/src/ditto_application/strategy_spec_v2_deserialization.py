"""Strict canonical V2 StrategySpec deserialization boundary."""

from __future__ import annotations

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
    StrategySpecV2,
)
from ditto_strategy.errors import StrategySpecError
from ditto_strategy.models import StrategySpecRecord

from ditto_application.exceptions import AppBuilderError
from ditto_application.strategy_spec_deserialization_components import (
    deserialize_param_constraint,
)
from ditto_application.strategy_spec_fields import (
    as_object_dict,
    as_sequence,
    as_str_tuple,
    read_bool,
    read_required_str,
    read_required_value,
)

__all__ = ["deserialize_strategy_spec_v2"]


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
