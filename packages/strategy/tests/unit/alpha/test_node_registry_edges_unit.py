"""Adversarial validation tests for the immutable node registry."""

from __future__ import annotations

from dataclasses import replace
from typing import cast

import pytest
from ditto_strategy.alpha.node_registry import (
    NodeConfigType,
    NodeDescriptor,
    NodeRegistry,
)
from ditto_strategy.alpha.nodes import NodeCategory, NodeRef
from ditto_strategy.alpha.specs import StrategyKind
from ditto_strategy.errors import StrategySpecError


def _descriptor() -> NodeDescriptor:
    return NodeDescriptor(
        node_type="builtin.test",
        version="1",
        category=NodeCategory.FACTOR_SET,
        display_name="Test",
        input_contract="universe_frame.v1",
        output_contract="factor_frame.v1",
        config_schema={"label": NodeConfigType.STRING},
        default_config={"label": "default"},
        required_datasets=("daily",),
        capability_tags=("deterministic",),
        supported_strategy_kinds=(StrategyKind.STOCK_SELECTION,),
        deterministic=True,
        implementation_key="builtin.test.v1",
    )


def test_descriptor_default_factories_produce_independent_empty_mappings() -> None:
    def build() -> NodeDescriptor:
        return NodeDescriptor(
            node_type="builtin.empty",
            version="1",
            category=NodeCategory.FILTER,
            display_name="Empty",
            input_contract="factor_frame.v1",
            output_contract="factor_frame.v1",
            supported_strategy_kinds=(StrategyKind.STOCK_SELECTION,),
            implementation_key="builtin.empty.v1",
        )

    first = build()
    second = build()

    assert first.config_schema == second.config_schema == {}
    assert first.default_config == second.default_config == {}
    assert first.config_schema is not second.config_schema
    assert first.default_config is not second.default_config


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("display_name", ""),
        ("input_contract", cast("str", 7)),
    ],
)
def test_descriptor_text_fields_must_be_non_empty(
    field_name: str,
    value: object,
) -> None:
    with pytest.raises(StrategySpecError) as exc_info:
        replace(_descriptor(), **{field_name: value})

    assert exc_info.value.details["reason"] == "invalid_descriptor_field"


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("required_datasets", ["daily"]),
        ("capability_tags", ("",)),
    ],
)
def test_descriptor_string_sets_require_typed_non_empty_tuples(
    field_name: str,
    value: object,
) -> None:
    with pytest.raises(StrategySpecError) as exc_info:
        replace(_descriptor(), **{field_name: value})

    assert exc_info.value.details["reason"] == "invalid_descriptor_field"


@pytest.mark.parametrize(
    "value",
    [[StrategyKind.STOCK_SELECTION], (), ("stock_selection",)],
)
def test_supported_strategy_kinds_require_a_non_empty_typed_tuple(
    value: object,
) -> None:
    with pytest.raises(StrategySpecError) as exc_info:
        replace(_descriptor(), supported_strategy_kinds=value)

    assert exc_info.value.details["reason"] == "invalid_descriptor_field"


@pytest.mark.parametrize(
    "schema",
    [
        [("label", NodeConfigType.STRING)],
        {cast("str", 1): NodeConfigType.STRING},
        {"label": cast("NodeConfigType", "string")},
    ],
)
def test_config_schema_requires_typed_mapping_entries(schema: object) -> None:
    with pytest.raises(StrategySpecError) as exc_info:
        replace(_descriptor(), config_schema=schema)

    assert exc_info.value.details["reason"] == "invalid_config_schema"


def test_json_config_accepts_canonical_values_and_serializes_enums() -> None:
    descriptor = replace(
        _descriptor(),
        config_schema={"payload": NodeConfigType.JSON},
        default_config={"payload": StrategyKind.STOCK_SELECTION},
    )

    resolved = descriptor.resolve_config({})
    manifest = NodeRegistry((descriptor,)).descriptors[0].manifest_payload()

    assert resolved["payload"] is StrategyKind.STOCK_SELECTION
    assert manifest["default_config"] == {"payload": "stock_selection"}


def test_array_config_rejects_scalar_value() -> None:
    descriptor = replace(
        _descriptor(),
        config_schema={"values": NodeConfigType.NUMBER_ARRAY},
        default_config={},
    )

    with pytest.raises(StrategySpecError) as exc_info:
        descriptor.resolve_config({"values": 1})

    assert exc_info.value.details["reason"] == "invalid_node_config_type"


def test_resolved_config_rejects_unknown_and_missing_fields() -> None:
    descriptor = replace(_descriptor(), default_config={})

    with pytest.raises(StrategySpecError) as unknown_exc:
        descriptor.resolve_config({"label": "value", "unknown": True})
    with pytest.raises(StrategySpecError) as missing_exc:
        descriptor.resolve_config({})

    assert unknown_exc.value.details["reason"] == "unknown_node_config_field"
    assert missing_exc.value.details["reason"] == "missing_node_config_field"


def test_descriptor_requires_typed_category_and_determinism() -> None:
    with pytest.raises(StrategySpecError) as category_exc:
        replace(_descriptor(), category=cast("NodeCategory", "factor_set"))
    with pytest.raises(StrategySpecError) as deterministic_exc:
        replace(_descriptor(), deterministic=cast("bool", 1))

    assert category_exc.value.details["reason"] == "invalid_descriptor_field"
    assert deterministic_exc.value.details["reason"] == "invalid_descriptor_field"


def test_registry_rejects_untyped_duplicate_entries_and_untyped_lookup() -> None:
    descriptor = _descriptor()

    with pytest.raises(StrategySpecError) as value_exc:
        NodeRegistry((object(),))
    with pytest.raises(StrategySpecError) as duplicate_exc:
        NodeRegistry((descriptor, descriptor))
    with pytest.raises(StrategySpecError) as lookup_exc:
        NodeRegistry((descriptor,)).lookup(cast("NodeRef", "builtin.test@1"))

    assert value_exc.value.details["reason"] == "invalid_descriptor_value"
    assert duplicate_exc.value.details["reason"] == "duplicate_descriptor_identity"
    assert lookup_exc.value.details["reason"] == "invalid_node_ref"


def test_registry_lookup_returns_the_exact_descriptor() -> None:
    descriptor = _descriptor()

    assert (
        NodeRegistry((descriptor,)).lookup(NodeRef("builtin.test", "1")) is descriptor
    )
