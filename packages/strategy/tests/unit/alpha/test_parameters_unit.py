"""Typed candidate parameter schema and binding tests."""

from __future__ import annotations

import math
from dataclasses import replace

import pytest
from ditto_strategy.alpha.node_registry import default_node_registry
from ditto_strategy.alpha.nodes import NodeRef, PipelineSpec
from ditto_strategy.alpha.spec_codec import adapt_legacy_strategy_spec
from ditto_strategy.alpha.specs import ParamConstraint, StrategySpec, StrategySpecV2
from ditto_strategy.errors import StrategySpecError


def _legacy_parameter_spec() -> StrategySpec:
    return StrategySpec(
        strategy_id="typed-parameter-spec",
        name="Typed parameter spec",
        template="etf_rotation",
        universe="csi_etf_broad",
        asset_class="etf",
        params={
            "allocation_method": "equal_weight",
            "enabled": True,
            "label": "baseline",
            "lookback": 20,
            "threshold": 0.10,
            "top_k": 5,
        },
        param_constraints=(
            ParamConstraint(
                name="allocation_method",
                dtype="str",
                allowed_values=("equal_weight", "score_weight"),
            ),
            ParamConstraint(name="enabled", dtype="bool"),
            ParamConstraint(name="label", dtype="str"),
            ParamConstraint(
                name="lookback",
                dtype="int",
                min_value=5,
                max_value=120,
                step=5,
            ),
            ParamConstraint(
                name="threshold",
                dtype="float",
                min_value=0.0,
                max_value=0.5,
                step=0.05,
            ),
            ParamConstraint(
                name="top_k",
                dtype="int",
                min_value=1,
                max_value=10,
                step=1,
            ),
        ),
    )


def _v2_parameter_spec() -> StrategySpecV2:
    return adapt_legacy_strategy_spec(_legacy_parameter_spec())


def _path(name: str) -> str:
    return f"/pipeline/nodes/legacy_factor_set/config/params/{name}"


def _assert_spec_invalid(
    exc_info: pytest.ExceptionInfo[StrategySpecError],
    *,
    reason: str,
) -> None:
    assert exc_info.value.details["code"] == "SPEC_INVALID"
    assert exc_info.value.details["reason"] == reason


def test_legacy_adapter_normalizes_parameter_names_to_stable_paths() -> None:
    """Legacy names become complete paths at the migration boundary."""
    legacy = StrategySpec(
        strategy_id="legacy-parameter-path",
        name="Legacy parameter path",
        template="etf_rotation",
        universe="csi_etf_broad",
        asset_class="etf",
        params={"lookback": 20},
        param_constraints=(
            ParamConstraint(
                name="lookback",
                dtype="int",
                min_value=5,
                max_value=120,
                step=5,
            ),
        ),
    )

    adapted = adapt_legacy_strategy_spec(legacy)

    assert adapted.parameter_schema[0].name == (
        "/pipeline/nodes/legacy_factor_set/config/params/lookback"
    )


def test_parameter_constraint_accepts_an_explicit_bool_type() -> None:
    """Bool is a first-class type and is not represented as integer."""
    constraint = ParamConstraint(name="enabled", dtype="bool")

    assert constraint.dtype == "bool"


def test_parameter_schema_resolves_exact_node_identity_and_value_types() -> None:
    """Schema resolution records the exact node version and derived enum type."""
    from ditto_strategy.alpha.parameters import ParameterSchema, ParameterValueType

    schema = ParameterSchema.from_spec(
        _v2_parameter_spec(),
        registry=default_node_registry(),
    )

    definitions = {item.path: item for item in schema.definitions}
    assert definitions[_path("enabled")].value_type is ParameterValueType.BOOLEAN
    assert definitions[_path("top_k")].value_type is ParameterValueType.INTEGER
    assert definitions[_path("threshold")].value_type is ParameterValueType.FLOAT
    assert definitions[_path("label")].value_type is ParameterValueType.STRING
    enum_definition = definitions[_path("allocation_method")]
    assert enum_definition.value_type is ParameterValueType.ENUM
    assert enum_definition.node_id == "legacy_factor_set"
    assert enum_definition.node_type == "legacy.factor_set"
    assert enum_definition.node_version == "1"


def test_parameter_binding_returns_new_frozen_resolved_spec_and_hashes() -> None:
    """Binding changes a copy while preserving base identity and canonical hashes."""
    from ditto_strategy.alpha.parameters import CandidateParameter, ParameterBinder
    from ditto_strategy.alpha.spec_codec import canonical_spec_hash

    base = _v2_parameter_spec()
    factor_before = next(
        node for node in base.pipeline.nodes if node.node_id == "legacy_factor_set"
    )
    binder = ParameterBinder(registry=default_node_registry())

    result = binder.bind(
        base,
        candidate_parameters=(
            CandidateParameter(path=_path("top_k"), value=3),
            CandidateParameter(path=_path("threshold"), value=0.20),
        ),
    )

    factor_after = next(
        node
        for node in result.resolved_spec.pipeline.nodes
        if node.node_id == "legacy_factor_set"
    )
    assert factor_before.config["params"]["top_k"] == 5
    assert factor_after.config["params"]["top_k"] == 3
    assert factor_after.config["params"]["threshold"] == 0.20
    assert result.base_spec is base
    assert result.resolved_spec is not base
    assert result.base_spec_hash == canonical_spec_hash(base)
    assert result.resolved_spec_hash == canonical_spec_hash(result.resolved_spec)
    assert result.resolved_spec_hash != result.base_spec_hash
    assert len(result.parameter_hash) == 64
    with pytest.raises(TypeError):
        factor_after.config["params"]["top_k"] = 9  # type: ignore[index]


def test_baseline_expands_complete_effective_values_with_stable_hash() -> None:
    """The empty candidate is explicit and hashes all schema-controlled values."""
    from ditto_strategy.alpha.parameters import ParameterBinder

    binder = ParameterBinder(registry=default_node_registry())

    first = binder.bind(_v2_parameter_spec(), candidate_parameters=())
    second = binder.bind(_v2_parameter_spec(), candidate_parameters=())

    assert tuple(item.path for item in first.effective_parameters) == tuple(
        sorted(
            (
                _path("allocation_method"),
                _path("enabled"),
                _path("label"),
                _path("lookback"),
                _path("threshold"),
                _path("top_k"),
            ),
        ),
    )
    assert {item.path: item.value for item in first.effective_parameters} == {
        _path("allocation_method"): "equal_weight",
        _path("enabled"): True,
        _path("label"): "baseline",
        _path("lookback"): 20,
        _path("threshold"): 0.10,
        _path("top_k"): 5,
    }
    assert first.parameter_hash == second.parameter_hash
    assert first.resolved_spec_hash == first.base_spec_hash


def test_parameter_hash_is_independent_of_candidate_input_order() -> None:
    """Candidate ordering does not alter resolved identity."""
    from ditto_strategy.alpha.parameters import CandidateParameter, ParameterBinder

    binder = ParameterBinder(registry=default_node_registry())
    candidates = (
        CandidateParameter(path=_path("top_k"), value=3),
        CandidateParameter(path=_path("lookback"), value=30),
    )

    forward = binder.bind(_v2_parameter_spec(), candidate_parameters=candidates)
    reverse = binder.bind(
        _v2_parameter_spec(),
        candidate_parameters=tuple(reversed(candidates)),
    )

    assert forward.effective_parameters == reverse.effective_parameters
    assert forward.parameter_hash == reverse.parameter_hash
    assert forward.resolved_spec_hash == reverse.resolved_spec_hash


@pytest.mark.parametrize(
    ("path", "value"),
    [
        pytest.param(_path("enabled"), False, id="bool"),
        pytest.param(_path("top_k"), 3, id="int"),
        pytest.param(_path("threshold"), 0.20, id="float"),
        pytest.param(_path("label"), "candidate", id="string"),
        pytest.param(
            _path("allocation_method"),
            "score_weight",
            id="enum",
        ),
    ],
)
def test_parameter_binding_accepts_each_exact_scalar_type(
    path: str,
    value: bool | int | float | str,
) -> None:
    """Every supported scalar type binds without coercion."""
    from ditto_strategy.alpha.parameters import CandidateParameter, ParameterBinder

    result = ParameterBinder(registry=default_node_registry()).bind(
        _v2_parameter_spec(),
        candidate_parameters=(CandidateParameter(path=path, value=value),),
    )

    assert {item.path: item.value for item in result.effective_parameters}[
        path
    ] == value
    assert type(
        {item.path: item.value for item in result.effective_parameters}[path],
    ) is type(value)


@pytest.mark.parametrize(
    ("path", "value"),
    [
        pytest.param(_path("enabled"), 1, id="int-is-not-bool"),
        pytest.param(_path("top_k"), True, id="bool-is-not-int"),
        pytest.param(_path("threshold"), 1, id="int-is-not-float"),
        pytest.param(_path("label"), False, id="bool-is-not-string"),
    ],
)
def test_parameter_binding_rejects_scalar_type_coercion(
    path: str,
    value: bool | int | float | str,
) -> None:
    """Candidate values use exact scalar types, including bool/int separation."""
    from ditto_strategy.alpha.parameters import CandidateParameter, ParameterBinder

    with pytest.raises(StrategySpecError) as exc_info:
        ParameterBinder(registry=default_node_registry()).bind(
            _v2_parameter_spec(),
            candidate_parameters=(CandidateParameter(path=path, value=value),),
        )

    _assert_spec_invalid(exc_info, reason="parameter_type_mismatch")


@pytest.mark.parametrize(
    ("path", "value", "reason"),
    [
        pytest.param(_path("top_k"), 11, "parameter_above_max", id="above-max"),
        pytest.param(_path("top_k"), 0, "parameter_below_min", id="below-min"),
        pytest.param(_path("lookback"), 22, "parameter_step_mismatch", id="step"),
        pytest.param(
            _path("allocation_method"),
            "risk_parity",
            "parameter_enum_mismatch",
            id="enum",
        ),
    ],
)
def test_parameter_binding_rejects_constraint_violations(
    path: str,
    value: bool | int | float | str,
    reason: str,
) -> None:
    """Range, step, and enum violations share stable SPEC_INVALID details."""
    from ditto_strategy.alpha.parameters import CandidateParameter, ParameterBinder

    with pytest.raises(StrategySpecError) as exc_info:
        ParameterBinder(registry=default_node_registry()).bind(
            _v2_parameter_spec(),
            candidate_parameters=(CandidateParameter(path=path, value=value),),
        )

    _assert_spec_invalid(exc_info, reason=reason)


def test_parameter_binding_rejects_unknown_and_duplicate_paths() -> None:
    """Unknown and repeated candidate paths fail instead of being ignored."""
    from ditto_strategy.alpha.parameters import CandidateParameter, ParameterBinder

    binder = ParameterBinder(registry=default_node_registry())
    with pytest.raises(StrategySpecError) as unknown:
        binder.bind(
            _v2_parameter_spec(),
            candidate_parameters=(CandidateParameter(path=_path("unknown"), value=1),),
        )
    _assert_spec_invalid(unknown, reason="unknown_parameter_path")

    repeated = CandidateParameter(path=_path("top_k"), value=3)
    with pytest.raises(StrategySpecError) as duplicate:
        binder.bind(
            _v2_parameter_spec(),
            candidate_parameters=(repeated, repeated),
        )
    _assert_spec_invalid(duplicate, reason="duplicate_parameter_binding")


def test_parameter_path_decodes_escaped_legacy_key_segments() -> None:
    """Slash and tilde remain unambiguous through RFC 6901 escaping."""
    from ditto_strategy.alpha.parameters import CandidateParameter, ParameterBinder

    legacy = StrategySpec(
        strategy_id="escaped-key",
        name="Escaped key",
        template="etf_rotation",
        universe="csi_etf_broad",
        asset_class="etf",
        params={"ratio/a~b": 2},
        param_constraints=(
            ParamConstraint(name="ratio/a~b", dtype="int", min_value=1, max_value=5),
        ),
    )
    base = adapt_legacy_strategy_spec(legacy)
    path = "/pipeline/nodes/legacy_factor_set/config/params/ratio~1a~0b"

    result = ParameterBinder(registry=default_node_registry()).bind(
        base,
        candidate_parameters=(CandidateParameter(path=path, value=4),),
    )

    assert result.effective_parameters[0].path == path
    assert result.effective_parameters[0].value == 4


def test_parameter_schema_rejects_non_path_duplicate_and_missing_target() -> None:
    """Native schema is complete, unique, and points at an existing config leaf."""
    from ditto_strategy.alpha.parameters import ParameterSchema

    base = _v2_parameter_spec()
    first = base.parameter_schema[0]
    cases = (
        (
            replace(base, parameter_schema=(replace(first, name="top_k"),)),
            "invalid_parameter_path",
        ),
        (replace(base, parameter_schema=(first, first)), "duplicate_parameter_path"),
        (
            replace(
                base,
                parameter_schema=(replace(first, name=_path("missing")),),
            ),
            "parameter_target_missing",
        ),
    )

    for invalid, reason in cases:
        with pytest.raises(StrategySpecError) as exc_info:
            ParameterSchema.from_spec(invalid, registry=default_node_registry())
        _assert_spec_invalid(exc_info, reason=reason)


def test_parameter_schema_rejects_unknown_node_version() -> None:
    """The target node's exact descriptor version must exist in the registry."""
    from ditto_strategy.alpha.parameters import ParameterSchema

    base = _v2_parameter_spec()
    factor = next(
        node for node in base.pipeline.nodes if node.node_id == "legacy_factor_set"
    )
    invalid_factor = replace(factor, ref=NodeRef("legacy.factor_set", "999"))
    invalid = replace(
        base,
        pipeline=PipelineSpec(
            nodes=tuple(
                invalid_factor if node.node_id == factor.node_id else node
                for node in base.pipeline.nodes
            ),
            sequence=base.pipeline.sequence,
        ),
    )

    with pytest.raises(StrategySpecError) as exc_info:
        ParameterSchema.from_spec(invalid, registry=default_node_registry())

    _assert_spec_invalid(exc_info, reason="unknown_parameter_node_version")


@pytest.mark.parametrize(
    ("constraint", "reason"),
    [
        pytest.param(
            ParamConstraint(name=_path("top_k"), dtype="int", min_value=5, max_value=1),
            "invalid_parameter_range",
            id="reversed-range",
        ),
        pytest.param(
            ParamConstraint(name=_path("top_k"), dtype="int", step=0),
            "invalid_parameter_step",
            id="zero-step",
        ),
        pytest.param(
            ParamConstraint(name=_path("top_k"), dtype="int", step=0.5),
            "invalid_parameter_step",
            id="fractional-int-step",
        ),
        pytest.param(
            ParamConstraint(name=_path("enabled"), dtype="bool", min_value=0),
            "invalid_parameter_constraints",
            id="bool-range",
        ),
        pytest.param(
            ParamConstraint(
                name=_path("allocation_method"),
                dtype="str",
                allowed_values=("equal_weight", "equal_weight"),
            ),
            "invalid_parameter_enum",
            id="duplicate-enum",
        ),
    ],
)
def test_parameter_schema_rejects_self_inconsistent_constraints(
    constraint: ParamConstraint,
    reason: str,
) -> None:
    """Schema constraint contradictions fail at schema resolution."""
    from ditto_strategy.alpha.parameters import ParameterSchema

    with pytest.raises(StrategySpecError) as exc_info:
        ParameterSchema.from_spec(
            replace(_v2_parameter_spec(), parameter_schema=(constraint,)),
            registry=default_node_registry(),
        )

    _assert_spec_invalid(exc_info, reason=reason)


def test_parameter_identity_collapses_signed_zero_without_mutating_hash_input() -> None:
    """All public parameter identities reuse the canonical float-zero rule."""
    from ditto_strategy.alpha.parameters import (
        EffectiveParameter,
        canonical_parameter_hash,
    )

    negative = EffectiveParameter(path=_path("threshold"), value=-0.0)
    positive = EffectiveParameter(path=_path("threshold"), value=0.0)

    assert math.copysign(1.0, negative.value) == 1.0
    assert canonical_parameter_hash((negative,)) == canonical_parameter_hash(
        (positive,),
    )

    bypassed = EffectiveParameter(path=_path("threshold"), value=0.0)
    object.__setattr__(bypassed, "value", -0.0)
    assert math.copysign(1.0, bypassed.value) == -1.0

    assert canonical_parameter_hash((bypassed,)) == canonical_parameter_hash(
        (positive,),
    )
    assert math.copysign(1.0, bypassed.value) == -1.0


@pytest.mark.parametrize(
    "invalid_value",
    [
        pytest.param(float("nan"), id="nan"),
        pytest.param(float("inf"), id="positive-infinity"),
        pytest.param(float("-inf"), id="negative-infinity"),
        pytest.param(10**100, id="huge-integer"),
        pytest.param("\ud800", id="lone-surrogate"),
    ],
)
def test_direct_parameter_values_fail_closed_without_raw_codec_errors(
    invalid_value: object,
) -> None:
    """Non-canonical typed values always raise stable StrategySpecError details."""
    from ditto_strategy.alpha.parameters import CandidateParameter, EffectiveParameter

    for parameter_type in (CandidateParameter, EffectiveParameter):
        with pytest.raises(StrategySpecError) as exc_info:
            parameter_type(path=_path("threshold"), value=invalid_value)

        _assert_spec_invalid(exc_info, reason="invalid_parameter_value")
        assert exc_info.value.details["path"] == _path("threshold")


@pytest.mark.parametrize(
    "invalid_value",
    [
        pytest.param(float("nan"), id="bypassed-nan"),
        pytest.param(float("inf"), id="bypassed-infinity"),
        pytest.param(10**100, id="bypassed-huge-integer"),
        pytest.param("\ud800", id="bypassed-lone-surrogate"),
    ],
)
def test_parameter_hash_revalidates_bypassed_values_without_codec_leaks(
    invalid_value: object,
) -> None:
    """Hashing is an independent fail-closed identity boundary."""
    from ditto_strategy.alpha.parameters import (
        EffectiveParameter,
        canonical_parameter_hash,
    )

    bypassed = EffectiveParameter(path=_path("threshold"), value=0.0)
    object.__setattr__(bypassed, "value", invalid_value)

    with pytest.raises(StrategySpecError) as exc_info:
        canonical_parameter_hash((bypassed,))

    _assert_spec_invalid(exc_info, reason="invalid_parameter_value")
    assert exc_info.value.details["path"] == _path("threshold")


def test_parameter_paths_fail_closed_when_they_have_no_utf8_identity() -> None:
    """Public DTO and hash boundaries reject non-UTF-8 paths uniformly."""
    from ditto_strategy.alpha.parameters import (
        CandidateParameter,
        EffectiveParameter,
        canonical_parameter_hash,
    )

    with pytest.raises(StrategySpecError) as direct:
        CandidateParameter(path="\ud800", value=1)

    _assert_spec_invalid(direct, reason="invalid_parameter_path")

    bypassed = EffectiveParameter(path=_path("threshold"), value=0.0)
    object.__setattr__(bypassed, "path", "\ud800")

    with pytest.raises(StrategySpecError) as hashed:
        canonical_parameter_hash((bypassed,))

    _assert_spec_invalid(hashed, reason="invalid_parameter_path")


def test_binder_canonicalizes_signed_zero_without_mutating_candidate() -> None:
    """Binding snapshots canonical zero while leaving the caller's DTO untouched."""
    from ditto_strategy.alpha.parameters import CandidateParameter, ParameterBinder

    candidate = CandidateParameter(path=_path("threshold"), value=0.0)
    object.__setattr__(candidate, "value", -0.0)

    negative = ParameterBinder(registry=default_node_registry()).bind(
        _v2_parameter_spec(),
        candidate_parameters=(candidate,),
    )
    positive = ParameterBinder(registry=default_node_registry()).bind(
        _v2_parameter_spec(),
        candidate_parameters=(CandidateParameter(path=_path("threshold"), value=0.0),),
    )

    effective_value = next(
        item.value
        for item in negative.effective_parameters
        if item.path == _path("threshold")
    )
    assert math.copysign(1.0, effective_value) == 1.0
    assert negative.parameter_hash == positive.parameter_hash
    assert negative.resolved_spec_hash == positive.resolved_spec_hash
    assert math.copysign(1.0, candidate.value) == -1.0


@pytest.mark.parametrize(
    ("invalid_candidates", "expected_path", "actual_type"),
    [
        pytest.param(object(), "candidate_parameters", "object", id="wrong-object"),
        pytest.param([], "candidate_parameters", "list", id="wrong-container"),
        pytest.param(
            (object(),),
            "candidate_parameters[0]",
            "object",
            id="wrong-tuple-element",
        ),
    ],
)
def test_binder_rejects_wrong_candidate_shapes_with_stable_details(
    invalid_candidates: object,
    expected_path: str,
    actual_type: str,
) -> None:
    """Runtime shape errors never leak Python or codec TypeError."""
    from ditto_strategy.alpha.parameters import ParameterBinder

    with pytest.raises(StrategySpecError) as exc_info:
        ParameterBinder(registry=default_node_registry()).bind(
            _v2_parameter_spec(),
            candidate_parameters=invalid_candidates,  # type: ignore[arg-type]
        )

    _assert_spec_invalid(exc_info, reason="invalid_candidate_parameters")
    assert exc_info.value.details["path"] == expected_path
    assert exc_info.value.details["actual_type"] == actual_type


def test_binder_revalidates_bypassed_path_before_hash_lookup() -> None:
    """An unhashable bypassed path cannot leak a native TypeError."""
    from ditto_strategy.alpha.parameters import CandidateParameter, ParameterBinder

    candidate = CandidateParameter(path=_path("threshold"), value=0.1)
    object.__setattr__(candidate, "path", [])

    with pytest.raises(StrategySpecError) as exc_info:
        ParameterBinder(registry=default_node_registry()).bind(
            _v2_parameter_spec(),
            candidate_parameters=(candidate,),
        )

    _assert_spec_invalid(exc_info, reason="invalid_parameter_path")
    assert candidate.path == []


def test_binder_wrong_spec_uses_typed_boundary_errors() -> None:
    """Wrong runtime spec objects fail through the public typed contract."""
    from ditto_strategy.alpha.parameters import ParameterBinder

    binder = ParameterBinder(registry=default_node_registry())
    with pytest.raises(StrategySpecError) as wrong_spec:
        binder.bind(
            object(),  # type: ignore[arg-type]
            candidate_parameters=(),
        )
    _assert_spec_invalid(wrong_spec, reason="invalid_parameter_spec")
    assert wrong_spec.value.details["path"] == "spec"


def _wide_step_spec() -> StrategySpecV2:
    return adapt_legacy_strategy_spec(
        StrategySpec(
            strategy_id="wide-step-spec",
            name="Wide step spec",
            template="etf_rotation",
            universe="csi_etf_broad",
            asset_class="etf",
            params={"float_value": 0.0, "int_value": 0},
            param_constraints=(
                ParamConstraint(
                    name="float_value",
                    dtype="float",
                    min_value=0.0,
                    max_value=100_000_000.0,
                    step=0.01,
                ),
                ParamConstraint(
                    name="int_value",
                    dtype="int",
                    min_value=0,
                    max_value=9_007_199_254_740_994,
                    step=2,
                ),
            ),
        ),
    )


def _decimal_step_spec(*, step: float, max_value: float) -> StrategySpecV2:
    return adapt_legacy_strategy_spec(
        StrategySpec(
            strategy_id="decimal-step-spec",
            name="Decimal step spec",
            template="etf_rotation",
            universe="csi_etf_broad",
            asset_class="etf",
            params={"float_value": 0.0},
            param_constraints=(
                ParamConstraint(
                    name="float_value",
                    dtype="float",
                    min_value=0.0,
                    max_value=max_value,
                    step=step,
                ),
            ),
        ),
    )


@pytest.mark.parametrize(
    ("step", "max_value", "value"),
    [
        pytest.param(0.07, 70_000_000.0, 70_000_000.0, id="large-007-grid"),
        pytest.param(0.1, 1.0, 0.3, id="decimal-03-grid"),
        pytest.param(1e-308, 1e308, 1e308, id="extreme-scale-grid"),
    ],
)
def test_decimal_float_step_accepts_canonical_aligned_values(
    step: float,
    max_value: float,
    value: float,
) -> None:
    """Decimal spellings define the grid even when binary division drifts."""
    from ditto_strategy.alpha.parameters import CandidateParameter, ParameterBinder

    result = ParameterBinder(registry=default_node_registry()).bind(
        _decimal_step_spec(step=step, max_value=max_value),
        candidate_parameters=(
            CandidateParameter(path=_path("float_value"), value=value),
        ),
    )

    assert {item.path: item.value for item in result.effective_parameters}[
        _path("float_value")
    ] == value


def test_decimal_float_step_rejects_large_half_step() -> None:
    """Exact decimal alignment cannot turn a large half-step into a grid point."""
    from ditto_strategy.alpha.parameters import CandidateParameter, ParameterBinder

    with pytest.raises(StrategySpecError) as exc_info:
        ParameterBinder(registry=default_node_registry()).bind(
            _decimal_step_spec(step=0.07, max_value=70_000_000.0),
            candidate_parameters=(
                CandidateParameter(
                    path=_path("float_value"),
                    value=35_000_000.035,
                ),
            ),
        )

    _assert_spec_invalid(exc_info, reason="parameter_step_mismatch")


def test_float_step_alignment_does_not_scale_tolerance_with_large_values() -> None:
    """A half-step remains invalid when the quotient is in the billions."""
    from ditto_strategy.alpha.parameters import CandidateParameter, ParameterBinder

    with pytest.raises(StrategySpecError) as exc_info:
        ParameterBinder(registry=default_node_registry()).bind(
            _wide_step_spec(),
            candidate_parameters=(
                CandidateParameter(
                    path=_path("float_value"),
                    value=50_000_000.005,
                ),
            ),
        )

    _assert_spec_invalid(exc_info, reason="parameter_step_mismatch")
    assert exc_info.value.details["path"] == _path("float_value")


def test_integer_step_alignment_remains_exact_above_float_precision() -> None:
    """An odd integer cannot become aligned through lossy float conversion."""
    from ditto_strategy.alpha.parameters import CandidateParameter, ParameterBinder

    with pytest.raises(StrategySpecError) as exc_info:
        ParameterBinder(registry=default_node_registry()).bind(
            _wide_step_spec(),
            candidate_parameters=(
                CandidateParameter(
                    path=_path("int_value"),
                    value=9_007_199_254_740_993,
                ),
            ),
        )

    _assert_spec_invalid(exc_info, reason="parameter_step_mismatch")
    assert exc_info.value.details["path"] == _path("int_value")


@pytest.mark.parametrize(
    ("path", "value"),
    [
        pytest.param(_path("float_value"), 0.0, id="float-minimum"),
        pytest.param(_path("float_value"), 0.3, id="float-rounding"),
        pytest.param(
            _path("float_value"),
            100_000_000.0,
            id="float-large-maximum",
        ),
        pytest.param(_path("int_value"), 0, id="integer-minimum"),
        pytest.param(
            _path("int_value"),
            9_007_199_254_740_994,
            id="integer-large-maximum",
        ),
    ],
)
def test_step_alignment_preserves_valid_float_and_integer_boundaries(
    path: str,
    value: float | int,
) -> None:
    """Strict tolerance still accepts aligned float and exact integer boundaries."""
    from ditto_strategy.alpha.parameters import CandidateParameter, ParameterBinder

    result = ParameterBinder(registry=default_node_registry()).bind(
        _wide_step_spec(),
        candidate_parameters=(CandidateParameter(path=path, value=value),),
    )

    assert {item.path: item.value for item in result.effective_parameters}[
        path
    ] == value
