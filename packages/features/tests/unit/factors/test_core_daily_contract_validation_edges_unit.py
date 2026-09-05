"""Fail-closed validation edges for governed daily-factor contracts."""

from __future__ import annotations

from dataclasses import replace
from typing import Literal, cast

import pytest
from ditto_features.factors.core_daily import (
    R3_CORE_FACTOR_CATALOG,
    AssetLane,
    CertifiedHistoryCoverage,
    CoreFactorCatalog,
    CoreFactorDescriptor,
    CoreFactorSpecContract,
    Lookback,
    LookbackUnit,
    PreprocessingStep,
)
from ditto_features.factors.spec import FactorSpec

pytestmark = pytest.mark.unit


def _descriptor(factor_id: str) -> CoreFactorDescriptor:
    return R3_CORE_FACTOR_CATALOG.by_id(factor_id)


def test_history_and_dataset_requirements_reject_untyped_or_ambiguous_inputs() -> None:
    requirement = _descriptor("momentum_1m").dataset_requirements[0].requirements[0]

    with pytest.raises(ValueError, match="non-negative int"):
        CertifiedHistoryCoverage(trading_days=-1)
    with pytest.raises(ValueError, match="dataset ID cannot be empty"):
        replace(requirement, dataset_id=" ")
    with pytest.raises(ValueError, match="required input fields must be non-empty"):
        replace(requirement, required_fields=())
    with pytest.raises(ValueError, match="invalid dataset lookback"):
        replace(requirement, lookback=cast(Lookback, object()))


def test_history_coverage_rejects_an_unregistered_lookback_unit() -> None:
    coverage = CertifiedHistoryCoverage(trading_days=20, reporting_periods=4)

    with pytest.raises(ValueError, match="unsupported lookback unit"):
        coverage.amount_for(cast(LookbackUnit, "calendar_days"))


def test_lane_requirements_are_non_empty_and_do_not_fallback_across_lanes() -> None:
    lane_requirement = _descriptor("quality_roe").dataset_requirements[0]

    assert lane_requirement.dataset_ids == ("balance_sheet", "income_statement")
    with pytest.raises(ValueError, match="lane dataset requirements must be non-empty"):
        replace(lane_requirement, requirements=())

    assert (
        R3_CORE_FACTOR_CATALOG.preprocessing.industry_requirements_for(AssetLane.ETF)
        == ()
    )


def test_materialized_intermediate_requires_a_unique_dependency_identity() -> None:
    intermediate = _descriptor("liquidity").materialized_intermediates[0]

    with pytest.raises(
        ValueError,
        match="materialized intermediate dependencies must be unique",
    ):
        replace(intermediate, dependencies=())


def test_preprocessing_rejects_duplicate_or_unscoped_execution_steps() -> None:
    preprocessing = R3_CORE_FACTOR_CATALOG.preprocessing

    with pytest.raises(ValueError, match="preprocessing steps must be unique"):
        replace(
            preprocessing,
            steps=(
                PreprocessingStep.PIT_ALIGNMENT,
                PreprocessingStep.PIT_ALIGNMENT,
            ),
        )
    with pytest.raises(ValueError, match="apply to at least one lane"):
        replace(preprocessing, applicable_lanes=frozenset())


def test_preprocessing_neutralization_lanes_must_be_supported() -> None:
    preprocessing = R3_CORE_FACTOR_CATALOG.preprocessing

    with pytest.raises(ValueError, match=r"industry neutralization.*unsupported lane"):
        replace(
            preprocessing,
            applicable_lanes=frozenset({AssetLane.ETF}),
            industry_neutralization_lanes=frozenset({AssetLane.STOCK}),
            size_neutralization_lanes=frozenset(),
        )
    with pytest.raises(ValueError, match=r"size neutralization.*unsupported lane"):
        replace(
            preprocessing,
            applicable_lanes=frozenset({AssetLane.ETF}),
            industry_neutralization_lanes=frozenset(),
            size_neutralization_lanes=frozenset({AssetLane.STOCK}),
            industry_input_requirements=(),
        )


def test_preprocessing_inputs_have_one_exact_contract_per_lane() -> None:
    preprocessing = R3_CORE_FACTOR_CATALOG.preprocessing
    industry = preprocessing.industry_input_requirements[0]

    with pytest.raises(ValueError, match="duplicate industry preprocessing"):
        replace(
            preprocessing,
            industry_input_requirements=(industry, industry),
        )
    with pytest.raises(
        ValueError,
        match=r"industry preprocessing.*do not match lanes",
    ):
        replace(preprocessing, industry_input_requirements=())


def test_factor_spec_contract_rejects_invalid_computation_identity() -> None:
    contract = _descriptor("momentum_1m").factor_spec

    with pytest.raises(ValueError, match="factor expression must be a string"):
        replace(contract, expression=cast(str, object()))
    with pytest.raises(ValueError, match="factor expression must be valid UTF-8"):
        replace(contract, expression="\ud800")
    with pytest.raises(ValueError, match="invalid factor computation type"):
        replace(
            contract,
            computation_type=cast(Literal["expression", "python"], "sql"),
        )
    with pytest.raises(ValueError, match="expression factor cannot be empty"):
        replace(contract, expression=" ")
    with pytest.raises(ValueError, match="Python factor cannot carry"):
        replace(contract, computation_type="python")


def test_factor_spec_contract_rejects_ambiguous_dependency_identity() -> None:
    contract = _descriptor("momentum_1m").factor_spec

    with pytest.raises(ValueError, match="factor spec dependencies must be unique"):
        replace(contract, dependencies=("market.close", "market.close"))
    with pytest.raises(ValueError, match="factor leaf dependencies must be non-empty"):
        replace(contract, leaf_dependencies=())
    with pytest.raises(ValueError, match="invalid factor dependency graph hash"):
        replace(contract, dependency_graph_hash="not-a-sha256")


def test_factor_spec_contract_rejects_a_recursive_dependency_cycle() -> None:
    root = FactorSpec(
        id="factor-a",
        expression="",
        dependencies=("factor-b",),
        computation_type="python",
    )
    upstream = FactorSpec(
        id="factor-b",
        expression="",
        dependencies=("factor-a",),
        computation_type="python",
    )

    with pytest.raises(ValueError, match="factor dependency cycle: factor-a"):
        CoreFactorSpecContract.from_spec(
            root,
            {"factor-a": root, "factor-b": upstream},
        )


def test_factor_descriptor_requires_exact_lane_contracts() -> None:
    descriptor = _descriptor("quality_roe")
    lane_requirement = descriptor.dataset_requirements[0]

    with pytest.raises(ValueError, match="support at least one lane"):
        replace(descriptor, lanes=frozenset())
    with pytest.raises(ValueError, match="duplicate lane dataset requirements"):
        replace(
            descriptor,
            dataset_requirements=(lane_requirement, lane_requirement),
        )
    with pytest.raises(ValueError, match="every supported lane needs"):
        replace(descriptor, dataset_requirements=())


def test_factor_descriptor_binds_benchmark_and_intermediate_identity() -> None:
    momentum = _descriptor("momentum_1m")
    liquidity = _descriptor("liquidity")
    intermediate = liquidity.materialized_intermediates[0]

    with pytest.raises(ValueError, match="benchmark requirement and flag must agree"):
        replace(momentum, benchmark_required=True)
    with pytest.raises(
        ValueError,
        match="materialized intermediate IDs must be unique",
    ):
        replace(
            liquidity,
            materialized_intermediates=(intermediate, intermediate),
        )


def test_factor_descriptor_does_not_fallback_to_an_unsupported_lane() -> None:
    with pytest.raises(ValueError, match="does not support lane 'etf'"):
        _descriptor("quality_roe").input_requirements_for(AssetLane.ETF)


def test_core_factor_catalog_rejects_empty_identity_and_unknown_lookup() -> None:
    with pytest.raises(ValueError, match="core factor IDs must be non-empty"):
        CoreFactorCatalog(
            descriptors=(),
            preprocessing=R3_CORE_FACTOR_CATALOG.preprocessing,
        )
    with pytest.raises(KeyError, match="missing-factor"):
        R3_CORE_FACTOR_CATALOG.by_id("missing-factor")
