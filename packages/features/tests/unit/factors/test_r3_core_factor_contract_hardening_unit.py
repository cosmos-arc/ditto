"""Regression tests for R3 governed-contract construction boundaries."""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping
from dataclasses import replace
from types import MappingProxyType

import pytest
from ditto_features.evaluation.report import (
    R3FactorDiagnosticsProjection,
    project_r3_factor_diagnostics,
)
from ditto_features.factors.core_daily import (
    R3_CORE_FACTOR_CATALOG,
    AssetLane,
    AvailabilityContext,
    AvailabilityReason,
    CertifiedBenchmarkEvidence,
    CertifiedHistoryCoverage,
    CoreFactorInputAvailability,
    Lookback,
    LookbackUnit,
    PitRequirement,
    assess_core_factor_input_availability,
)
from ditto_features.factors.factor_specs import ALL_FACTOR_SPECS
from ditto_features.factors.production_guard import validate_r3_core_factor_catalog
from ditto_features.factors.spec import FactorContext


def _runtime_construct[T](
    factory: Callable[..., T],
    /,
    **kwargs: object,
) -> T:
    """Exercise runtime DTO boundaries without weakening production types."""
    return factory(**kwargs)


def _runtime_replace[T](value: T, /, **changes: object) -> T:
    """Inject runtime values through dataclasses.replace for boundary tests."""
    return replace(value, **changes)


def _descriptor(factor_id: str):
    return R3_CORE_FACTOR_CATALOG.by_id(factor_id)


def test_catalog_and_nested_sequence_inputs_are_defensively_copied() -> None:
    descriptor_source = list(R3_CORE_FACTOR_CATALOG.descriptors)
    catalog = _runtime_replace(
        R3_CORE_FACTOR_CATALOG,
        descriptors=descriptor_source,
    )
    original_hash = catalog.payload_hash
    descriptor_source.pop()
    assert isinstance(catalog.descriptors, tuple)
    assert len(catalog.descriptors) == 12
    assert catalog.payload_hash == original_hash

    requirement = _descriptor("momentum_1m").input_requirements_for(AssetLane.STOCK)[0]
    field_source = list(requirement.required_fields)
    copied_requirement = _runtime_replace(requirement, required_fields=field_source)
    field_source.clear()
    assert copied_requirement.required_fields == ("market.close",)

    lane_requirement = _descriptor("momentum_1m").dataset_requirements[0]
    requirement_source = list(lane_requirement.requirements)
    copied_lane = _runtime_replace(lane_requirement, requirements=requirement_source)
    requirement_source.clear()
    assert copied_lane.requirements == lane_requirement.requirements

    intermediate = _descriptor("liquidity").materialized_intermediates[0]
    dependency_source = list(intermediate.dependencies)
    copied_intermediate = _runtime_replace(
        intermediate,
        dependencies=dependency_source,
    )
    dependency_source.clear()
    assert copied_intermediate.dependencies == ("market.amount",)

    preprocessing = R3_CORE_FACTOR_CATALOG.preprocessing
    step_source = list(preprocessing.steps)
    industry_source = list(preprocessing.industry_input_requirements)
    size_source = list(preprocessing.size_input_requirements)
    copied_preprocessing = _runtime_replace(
        preprocessing,
        steps=step_source,
        industry_input_requirements=industry_source,
        size_input_requirements=size_source,
    )
    step_source.clear()
    industry_source.clear()
    size_source.clear()
    assert copied_preprocessing.steps == preprocessing.steps
    assert copied_preprocessing.industry_input_requirements == (
        preprocessing.industry_input_requirements
    )
    assert copied_preprocessing.size_input_requirements == (
        preprocessing.size_input_requirements
    )

    spec_contract = _descriptor("liquidity").factor_spec
    spec_dependency_source = list(spec_contract.dependencies)
    leaf_source = list(spec_contract.leaf_dependencies)
    copied_spec = _runtime_replace(
        spec_contract,
        dependencies=spec_dependency_source,
        leaf_dependencies=leaf_source,
    )
    spec_dependency_source.clear()
    leaf_source.clear()
    assert copied_spec.dependencies == spec_contract.dependencies
    assert copied_spec.leaf_dependencies == spec_contract.leaf_dependencies

    descriptor_requirement_source = list(_descriptor("liquidity").dataset_requirements)
    intermediate_source = list(_descriptor("liquidity").materialized_intermediates)
    copied_descriptor = _runtime_replace(
        _descriptor("liquidity"),
        dataset_requirements=descriptor_requirement_source,
        materialized_intermediates=intermediate_source,
    )
    descriptor_requirement_source.clear()
    intermediate_source.clear()
    assert copied_descriptor.dataset_requirements == (
        _descriptor("liquidity").dataset_requirements
    )
    assert copied_descriptor.materialized_intermediates == (
        _descriptor("liquidity").materialized_intermediates
    )


def test_availability_and_projection_sequences_are_defensively_copied() -> None:
    dataset_source = ["stock_daily"]
    missing_source = ["market.close"]
    availability = _runtime_construct(
        CoreFactorInputAvailability,
        certified_inputs_available=False,
        reason=AvailabilityReason.UNCERTIFIED_INPUT_FIELD,
        dataset_ids=dataset_source,
        missing_fields=missing_source,
    )
    dataset_source.clear()
    missing_source.clear()
    assert availability.dataset_ids == ("stock_daily",)
    assert availability.missing_fields == ("market.close",)

    metric_source = ["coverage"]
    projection = _runtime_construct(
        R3FactorDiagnosticsProjection,
        computed_metrics=metric_source,
        values={"coverage": 1},
    )
    metric_source.clear()
    assert projection.computed_metrics == ("coverage",)
    assert projection.values == {"coverage": 1.0}


@pytest.mark.parametrize("bad_sequence", ["abc", b"abc"])
def test_sequence_contracts_reject_text_like_inputs(bad_sequence: object) -> None:
    requirement = _descriptor("momentum_1m").input_requirements_for(AssetLane.STOCK)[0]
    with pytest.raises(ValueError, match="sequence"):
        _runtime_replace(requirement, required_fields=bad_sequence)
    with pytest.raises(ValueError, match="sequence"):
        _runtime_construct(
            CoreFactorInputAvailability,
            certified_inputs_available=False,
            dataset_ids=bad_sequence,
        )
    with pytest.raises(ValueError, match="sequence"):
        _runtime_construct(
            R3FactorDiagnosticsProjection,
            computed_metrics=bad_sequence,
            values={},
        )


@pytest.mark.parametrize(
    "bad_sequence_factory",
    [
        lambda: {"market.close"},
        lambda: (item for item in ("market.close",)),
    ],
    ids=("set", "generator"),
)
def test_sequence_contracts_reject_non_sequence_iterables(
    bad_sequence_factory: Callable[[], object],
) -> None:
    requirement = _descriptor("momentum_1m").input_requirements_for(AssetLane.STOCK)[0]
    with pytest.raises(ValueError, match="sequence"):
        _runtime_replace(
            requirement,
            required_fields=bad_sequence_factory(),
        )
    with pytest.raises(ValueError, match="sequence"):
        _runtime_construct(
            CoreFactorInputAvailability,
            certified_inputs_available=False,
            dataset_ids=bad_sequence_factory(),
        )
    with pytest.raises(ValueError, match="sequence"):
        _runtime_construct(
            R3FactorDiagnosticsProjection,
            computed_metrics=bad_sequence_factory(),
            values={"market.close": 1},
        )


def test_projection_constructor_enforces_registered_metric_shapes() -> None:
    with pytest.raises(ValueError, match="finite number"):
        R3FactorDiagnosticsProjection(
            computed_metrics=("coverage",),
            values={"coverage": math.nan},
        )
    with pytest.raises(ValueError, match="unsupported R3 diagnostic metric"):
        R3FactorDiagnosticsProjection(
            computed_metrics=("made_up",),
            values={"made_up": True},
        )
    with pytest.raises(ValueError, match="numeric mapping"):
        R3FactorDiagnosticsProjection(
            computed_metrics=("exposure",),
            values={"exposure": {"industry": {"bank": True}}},
        )


def test_projection_constructor_and_projector_share_normalization() -> None:
    decay_source = [[1, 0.3]]
    exposure_source = {"industry": {"bank": 0.2}}
    direct = R3FactorDiagnosticsProjection(
        computed_metrics=("coverage", "decay", "exposure"),
        values={
            "coverage": 1,
            "decay": decay_source,
            "exposure": exposure_source,
        },
    )
    projected = project_r3_factor_diagnostics(
        {
            "coverage": 1,
            "ic_decay": [[1, 0.3]],
            "factor_exposure": {"industry": {"bank": 0.2}},
        }
    )
    decay_source[0][1] = 9.9
    exposure_source["industry"]["bank"] = 9.9

    assert direct == projected
    assert direct.values["decay"] == ((1, 0.3),)
    exposure = direct.values["exposure"]
    assert isinstance(exposure, Mapping)
    assert isinstance(exposure, MappingProxyType)
    assert exposure["industry"]["bank"] == 0.2


def _stock_context(
    factor_id: str,
    *,
    pit_by_dataset: Mapping[str, PitRequirement],
    benchmark: CertifiedBenchmarkEvidence | None = None,
) -> AvailabilityContext:
    descriptor = _descriptor(factor_id)
    requirements = [
        *descriptor.input_requirements_for(AssetLane.STOCK),
        *R3_CORE_FACTOR_CATALOG.preprocessing.industry_requirements_for(
            AssetLane.STOCK
        ),
    ]
    if descriptor.neutralize_size:
        requirements.extend(
            R3_CORE_FACTOR_CATALOG.preprocessing.size_requirements_for(AssetLane.STOCK)
        )
    datasets = frozenset(item.dataset_id for item in requirements)
    return AvailabilityContext(
        lane=AssetLane.STOCK,
        certified_datasets=datasets,
        certified_history={
            dataset_id: CertifiedHistoryCoverage(500, 8) for dataset_id in datasets
        },
        certified_fields={
            dataset_id: frozenset(
                field_id
                for item in requirements
                if item.dataset_id == dataset_id
                for field_id in item.required_fields
            )
            for dataset_id in datasets
        },
        benchmark_id=None if benchmark is None else benchmark.benchmark_id,
        certified_benchmarks=(
            {} if benchmark is None else {benchmark.benchmark_id: benchmark}
        ),
        certified_pit=pit_by_dataset,
    )


def test_dataset_pit_evidence_requires_sufficient_strength() -> None:
    known_at = {
        "income_statement": PitRequirement.KNOWN_AT,
        "industry_mapping": PitRequirement.KNOWN_AT,
        "valuation_metrics": PitRequirement.KNOWN_AT,
    }
    insufficient = assess_core_factor_input_availability(
        _descriptor("revenue_growth"),
        _stock_context("revenue_growth", pit_by_dataset=known_at),
    )
    assert insufficient.certified_inputs_available is False
    assert insufficient.reason is AvailabilityReason.PIT_ALIGNMENT_MISSING
    assert insufficient.dataset_ids == ("income_statement",)

    sufficient = dict(known_at)
    sufficient["income_statement"] = PitRequirement.ANNOUNCEMENT_KNOWN_AT
    assert assess_core_factor_input_availability(
        _descriptor("revenue_growth"),
        _stock_context("revenue_growth", pit_by_dataset=sufficient),
    ).certified_inputs_available


def test_benchmark_pit_evidence_requires_sufficient_strength() -> None:
    pit_by_dataset = {
        "stock_daily": PitRequirement.KNOWN_AT,
        "adj_factor": PitRequirement.KNOWN_AT,
        "industry_mapping": PitRequirement.KNOWN_AT,
        "valuation_metrics": PitRequirement.KNOWN_AT,
    }
    weak = CertifiedBenchmarkEvidence(
        benchmark_id="000300.SH",
        dataset_id="index_daily",
        certified_fields=frozenset({"benchmark.close"}),
        certified_history=CertifiedHistoryCoverage(60, 0),
        certified_pit=PitRequirement.NONE,
    )
    insufficient = assess_core_factor_input_availability(
        _descriptor("relative_strength_60d"),
        _stock_context(
            "relative_strength_60d",
            pit_by_dataset=pit_by_dataset,
            benchmark=weak,
        ),
    )
    assert insufficient.reason is AvailabilityReason.PIT_ALIGNMENT_MISSING

    sufficient = replace(weak, certified_pit=PitRequirement.KNOWN_AT)
    assert assess_core_factor_input_availability(
        _descriptor("relative_strength_60d"),
        _stock_context(
            "relative_strength_60d",
            pit_by_dataset=pit_by_dataset,
            benchmark=sufficient,
        ),
    ).certified_inputs_available


def test_effective_lookback_governs_market_history_requirements() -> None:
    expected = {
        "momentum_1m": 20,
        "momentum_3m": 60,
        "reversal_1w": 5,
        "liquidity": 21,
        "volatility_factor": 21,
        "vol_ratio": 61,
        "relative_strength_60d": 60,
    }
    for factor_id, history in expected.items():
        descriptor = _descriptor(factor_id)
        assert descriptor.factor_spec.effective_lookback <= history
        for lane in descriptor.lanes:
            assert all(
                requirement.lookback.value == history
                for requirement in descriptor.input_requirements_for(lane)
            )
    assert _descriptor("liquidity").materialized_intermediates[0].lookback == (
        Lookback(21, LookbackUnit.TRADING_DAYS)
    )


def test_guard_rejects_dataset_history_below_effective_lookback() -> None:
    descriptor = _descriptor("volatility_factor")
    stock_lane = descriptor.dataset_requirements[0]
    undersized_market = replace(
        stock_lane.requirements[0],
        lookback=Lookback(20, LookbackUnit.TRADING_DAYS),
    )
    undersized_lane = replace(
        stock_lane,
        requirements=(undersized_market, *stock_lane.requirements[1:]),
    )
    undersized_descriptor = replace(
        descriptor,
        dataset_requirements=(undersized_lane, *descriptor.dataset_requirements[1:]),
    )
    catalog = replace(
        R3_CORE_FACTOR_CATALOG,
        descriptors=(
            *R3_CORE_FACTOR_CATALOG.descriptors[:3],
            undersized_descriptor,
            *R3_CORE_FACTOR_CATALOG.descriptors[4:],
        ),
    )
    with pytest.raises(ValueError, match="effective lookback"):
        validate_r3_core_factor_catalog(catalog)


def test_calendar_context_is_part_of_factor_graph_identity(monkeypatch) -> None:
    original = ALL_FACTOR_SPECS["momentum_1m"]
    monkeypatch.setitem(
        ALL_FACTOR_SPECS,
        "momentum_1m",
        replace(
            original,
            calendar_context=FactorContext(
                is_special=True,
                is_half_day=False,
                exchange="SSE",
            ),
        ),
    )
    with pytest.raises(ValueError, match="factor spec contract drifted"):
        validate_r3_core_factor_catalog(R3_CORE_FACTOR_CATALOG)
