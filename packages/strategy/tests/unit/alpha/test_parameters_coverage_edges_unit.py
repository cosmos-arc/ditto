"""Fail-closed edge coverage for typed candidate parameter contracts."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import replace
from typing import cast

import pytest
from ditto_strategy.alpha.node_registry import default_node_registry
from ditto_strategy.alpha.nodes import PipelineSpec
from ditto_strategy.alpha.parameters import (
    EffectiveParameter,
    ParameterDefinition,
    ParameterSchema,
    ParameterValueType,
    canonical_parameter_hash,
)
from ditto_strategy.alpha.spec_codec import adapt_legacy_strategy_spec
from ditto_strategy.alpha.specs import ParamConstraint, StrategySpec, StrategySpecV2
from ditto_strategy.errors import StrategySpecError


def _path(name: str) -> str:
    return f"/pipeline/nodes/legacy_factor_set/config/params/{name}"


def _parameter_spec() -> StrategySpecV2:
    return adapt_legacy_strategy_spec(
        StrategySpec(
            strategy_id="parameter-edge-contract",
            name="Parameter edge contract",
            template="etf_rotation",
            universe="csi_etf_broad",
            asset_class="etf",
            params={
                "enabled": True,
                "nested": {"leaf": 1},
                "top_k": 5,
            },
            param_constraints=(ParamConstraint(name="top_k", dtype="int"),),
        ),
    )


def _spec_with_constraint(
    name: str,
    *,
    dtype: str = "int",
    allowed_values: tuple[str, ...] = (),
) -> StrategySpecV2:
    return replace(
        _parameter_spec(),
        parameter_schema=(
            ParamConstraint(
                name=name,
                dtype=dtype,
                allowed_values=allowed_values,
            ),
        ),
    )


def _spec_with_factor_config(config: Mapping[str, object]) -> StrategySpecV2:
    spec = _parameter_spec()
    factor = next(
        node for node in spec.pipeline.nodes if node.node_id == "legacy_factor_set"
    )
    changed_factor = replace(factor, config=config)
    return replace(
        spec,
        pipeline=PipelineSpec(
            nodes=tuple(
                changed_factor if node.node_id == factor.node_id else node
                for node in spec.pipeline.nodes
            ),
            sequence=spec.pipeline.sequence,
        ),
    )


def _assert_invalid(
    exc_info: pytest.ExceptionInfo[StrategySpecError],
    *,
    reason: str,
) -> None:
    assert exc_info.value.details["code"] == "SPEC_INVALID"
    assert exc_info.value.details["reason"] == reason


def test_parameter_definition_rejects_non_scalar_runtime_values() -> None:
    """Resolved definitions independently enforce the canonical scalar boundary."""
    definition = ParameterDefinition(
        path=_path("top_k"),
        value_type=ParameterValueType.INTEGER,
        node_id="legacy_factor_set",
        node_type="legacy.factor_set",
        node_version="1",
        config_path=("params", "top_k"),
    )

    with pytest.raises(StrategySpecError) as exc_info:
        definition.validate_value(object())

    _assert_invalid(exc_info, reason="invalid_parameter_value")
    assert exc_info.value.details["path"] == _path("top_k")
    assert exc_info.value.details["actual_type"] == "object"


@pytest.mark.parametrize(
    "path",
    [
        pytest.param(
            "/pipeline/nodes/legacy_factor_set/config/params/top~2k",
            id="invalid-rfc6901-escape",
        ),
        pytest.param(
            "/pipeline/nodes/legacy_factor_set/config",
            id="incomplete-path",
        ),
        pytest.param(
            "/pipelines/nodes/legacy_factor_set/config/params/top_k",
            id="wrong-root",
        ),
    ],
)
def test_parameter_schema_rejects_noncanonical_path_shapes(path: str) -> None:
    """Invalid escapes, incomplete paths, and wrong roots fail at schema parsing."""
    with pytest.raises(StrategySpecError) as exc_info:
        ParameterSchema.from_spec(
            _spec_with_constraint(path),
            registry=default_node_registry(),
        )

    _assert_invalid(exc_info, reason="invalid_parameter_path")
    assert exc_info.value.details["path"] == path


def test_parameter_schema_rejects_a_path_that_crosses_a_scalar_config() -> None:
    """Every path segment before the leaf must resolve to a config object."""
    invalid = _spec_with_factor_config({"params": 1})

    with pytest.raises(StrategySpecError) as exc_info:
        ParameterSchema.from_spec(invalid, registry=default_node_registry())

    _assert_invalid(exc_info, reason="parameter_target_missing")
    assert exc_info.value.details["missing_segment"] == "top_k"


def test_numeric_parameter_cannot_declare_string_enum_values() -> None:
    """Numeric and boolean parameter types cannot be disguised as string enums."""
    invalid = _spec_with_constraint(
        _path("enabled"),
        dtype="bool",
        allowed_values=("enabled", "disabled"),
    )

    with pytest.raises(StrategySpecError) as exc_info:
        ParameterSchema.from_spec(invalid, registry=default_node_registry())

    _assert_invalid(exc_info, reason="invalid_parameter_enum")
    assert exc_info.value.details["path"] == _path("enabled")


@pytest.mark.parametrize(
    ("path", "missing_segment"),
    [
        pytest.param(
            "/pipeline/nodes/missing/config/params/top_k",
            None,
            id="unknown-node",
        ),
        pytest.param(
            "/pipeline/nodes/legacy_factor_set/config/unknown_field",
            "unknown_field",
            id="unknown-config-field",
        ),
    ],
)
def test_parameter_schema_rejects_unknown_node_and_descriptor_fields(
    path: str,
    missing_segment: str | None,
) -> None:
    """Paths must resolve through both the pipeline and its registered descriptor."""
    with pytest.raises(StrategySpecError) as exc_info:
        ParameterSchema.from_spec(
            _spec_with_constraint(path),
            registry=default_node_registry(),
        )

    _assert_invalid(exc_info, reason="parameter_target_missing")
    assert exc_info.value.details["path"] == path
    if missing_segment is None:
        assert exc_info.value.details["node_id"] == "missing"
    else:
        assert exc_info.value.details["missing_segment"] == missing_segment


@pytest.mark.parametrize(
    ("values", "expected_path", "actual_type"),
    [
        pytest.param(
            cast(Sequence[EffectiveParameter], object()),
            "effective_parameters",
            "object",
            id="non-sequence",
        ),
        pytest.param(
            cast(Sequence[EffectiveParameter], (object(),)),
            "effective_parameters[0]",
            "object",
            id="untyped-member",
        ),
    ],
)
def test_parameter_hash_rejects_invalid_runtime_sequence_shapes(
    values: Sequence[EffectiveParameter],
    expected_path: str,
    actual_type: str,
) -> None:
    """Hashing rejects invalid containers and members with stable typed errors."""
    with pytest.raises(StrategySpecError) as exc_info:
        canonical_parameter_hash(values)

    _assert_invalid(exc_info, reason="invalid_effective_parameters")
    assert exc_info.value.details["path"] == expected_path
    assert exc_info.value.details["actual_type"] == actual_type


def test_parameter_hash_rejects_duplicate_effective_paths() -> None:
    """One canonical parameter identity cannot contain duplicate path keys."""
    first = EffectiveParameter(path=_path("top_k"), value=3)
    second = EffectiveParameter(path=_path("top_k"), value=5)

    with pytest.raises(StrategySpecError) as exc_info:
        canonical_parameter_hash((first, second))

    _assert_invalid(exc_info, reason="duplicate_effective_parameter")
    assert exc_info.value.details["path"] == "effective_parameters"
