"""Boundary validation for portfolio optimization policies and inputs."""

from __future__ import annotations

from typing import Literal, cast

import numpy as np
import pytest
from ditto_kernel.identity import InstrumentId
from ditto_portfolio.rebalancing._optimization_input import (
    OptimizationInputError,
    prepare_input,
    subset_prepared_input,
)
from ditto_portfolio.rebalancing.optimization_models import (
    OptimizationMethod,
    PortfolioConstructionPolicy,
    PortfolioOptimizationRequest,
)


def _policy(**changes: object) -> PortfolioConstructionPolicy:
    values: dict[str, object] = {
        "policy_id": "policy-v1",
        "version": 1,
        "method": OptimizationMethod.MVO,
        "min_observations": 2,
    }
    values.update(changes)
    return PortfolioConstructionPolicy(
        policy_id=cast(str, values["policy_id"]),
        version=cast(int, values["version"]),
        method=cast(OptimizationMethod, values["method"]),
        execution_mode=cast(
            Literal["shadow", "enforced"],
            values.get("execution_mode", "enforced"),
        ),
        lookback_sessions=cast(int, values.get("lookback_sessions", 250)),
        min_observations=cast(int, values["min_observations"]),
        confidence_level=cast(float, values.get("confidence_level", 0.99)),
        turnover_penalty_bps=cast(float, values.get("turnover_penalty_bps", 10.0)),
        max_candidates=cast(int, values.get("max_candidates", 500)),
        cash_target=cast(float, values.get("cash_target", 0.0)),
        max_weight=cast(float, values.get("max_weight", 1.0)),
        min_weight=cast(float, values.get("min_weight", 0.0)),
        max_positions=cast(int | None, values.get("max_positions")),
        max_turnover=cast(float | None, values.get("max_turnover")),
        industry_caps=cast(
            tuple[tuple[str, float], ...], values.get("industry_caps", ())
        ),
        solver_timeout_seconds=cast(float, values.get("solver_timeout_seconds", 10.0)),
        constraint_tolerance=cast(float, values.get("constraint_tolerance", 1e-6)),
        risk_contribution_tolerance=cast(
            float, values.get("risk_contribution_tolerance", 1e-4)
        ),
    )


def _request(**changes: object) -> PortfolioOptimizationRequest:
    values: dict[str, object] = {
        "policy": _policy(),
        "instrument_ids": (InstrumentId(1), InstrumentId(2)),
        "covariance": np.eye(2),
        "scenario_returns": None,
        "candidate_weights": (0.5, 0.5),
        "current_weights": (0.5, 0.5),
        "source_snapshot_ids": ("snapshot-1",),
        "expected_returns": None,
        "industries": None,
        "eligible": None,
    }
    values.update(changes)
    return PortfolioOptimizationRequest(
        policy=cast(PortfolioConstructionPolicy, values["policy"]),
        instrument_ids=cast(tuple[InstrumentId, ...], values["instrument_ids"]),
        covariance=cast(np.ndarray, values["covariance"]),
        scenario_returns=cast(np.ndarray | None, values["scenario_returns"]),
        candidate_weights=cast(tuple[float, ...], values["candidate_weights"]),
        current_weights=cast(tuple[float, ...], values["current_weights"]),
        source_snapshot_ids=cast(tuple[str, ...], values["source_snapshot_ids"]),
        expected_returns=cast(tuple[float, ...] | None, values["expected_returns"]),
        industries=cast(tuple[str | None, ...] | None, values["industries"]),
        eligible=cast(tuple[bool, ...] | None, values["eligible"]),
    )


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"policy_id": " "}, "policy_id"),
        ({"version": 0}, "version"),
        ({"execution_mode": "dry-run"}, "execution_mode"),
        ({"lookback_sessions": 1}, "lookback_sessions"),
        ({"min_observations": 1}, "min_observations"),
        ({"cash_target": 1.0}, "cash_target"),
        ({"max_weight": 0.0}, "max_weight"),
        ({"min_weight": 0.6, "max_weight": 0.5}, "min_weight"),
        ({"confidence_level": 1.0}, "confidence_level"),
        ({"industry_caps": ((" ", 0.5),)}, "industry caps"),
        ({"turnover_penalty_bps": float("nan")}, "finite"),
        ({"turnover_penalty_bps": -0.1}, "turnover_penalty_bps"),
        ({"max_candidates": 0}, "max_candidates"),
        ({"max_positions": 0}, "max_positions"),
        ({"max_turnover": -0.1}, "max_turnover"),
        ({"solver_timeout_seconds": 0.0}, "solver_timeout_seconds"),
        ({"constraint_tolerance": 0.0}, "constraint_tolerance"),
        ({"risk_contribution_tolerance": 0.0}, "risk_contribution_tolerance"),
    ],
)
def test_policy_rejects_unsafe_or_ambiguous_limits(
    changes: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        _policy(**changes)


def test_input_rejects_capacity_empty_and_duplicate_universes() -> None:
    with pytest.raises(OptimizationInputError) as capacity:
        prepare_input(_request(policy=_policy(max_candidates=1)))
    assert capacity.value.code == "candidate_capacity_exceeded"

    with pytest.raises(OptimizationInputError) as empty:
        prepare_input(
            _request(
                instrument_ids=(),
                covariance=np.empty((0, 0)),
                candidate_weights=(),
                current_weights=(),
            )
        )
    assert empty.value.code == "invalid_universe"

    with pytest.raises(OptimizationInputError) as duplicate:
        prepare_input(_request(instrument_ids=(InstrumentId(1), InstrumentId(1))))
    assert duplicate.value.code == "invalid_universe"


@pytest.mark.parametrize(
    "changes",
    [
        {"candidate_weights": (1.0,)},
        {"current_weights": (1.0,)},
    ],
)
def test_input_rejects_weight_shape_mismatch(changes: dict[str, object]) -> None:
    with pytest.raises(OptimizationInputError) as exc_info:
        prepare_input(_request(**changes))
    assert exc_info.value.code == "shape_mismatch"


def test_input_rejects_weight_above_total_portfolio() -> None:
    with pytest.raises(OptimizationInputError) as exc_info:
        prepare_input(_request(candidate_weights=(0.6, 0.5)))
    assert exc_info.value.code == "invalid_weights"


def test_max_positions_selects_highest_ranked_eligible_assets_deterministically() -> (
    None
):
    prepared = prepare_input(
        _request(
            policy=_policy(max_positions=1),
            candidate_weights=(0.4, 0.6),
            current_weights=(0.4, 0.6),
        )
    )
    assert prepared.indices == (1,)


def test_input_rejects_empty_eligible_universe() -> None:
    with pytest.raises(OptimizationInputError) as exc_info:
        prepare_input(_request(eligible=(False, False)))
    assert exc_info.value.code == "empty_eligible_universe"


def test_covariance_requires_finite_square_positive_semidefinite_matrix() -> None:
    with pytest.raises(OptimizationInputError) as shape:
        prepare_input(_request(covariance=np.ones((1, 2))))
    assert shape.value.code == "invalid_covariance"

    with pytest.raises(OptimizationInputError) as negative:
        prepare_input(_request(covariance=np.array([[1.0, 2.0], [2.0, 1.0]])))
    assert negative.value.code == "covariance_not_psd"


def test_historical_cvar_requires_finite_two_dimensional_scenarios() -> None:
    policy = _policy(method=OptimizationMethod.HISTORICAL_CVAR)
    with pytest.raises(OptimizationInputError) as missing:
        prepare_input(_request(policy=policy))
    assert missing.value.code == "insufficient_scenarios"

    with pytest.raises(OptimizationInputError) as shape:
        prepare_input(_request(policy=policy, scenario_returns=np.ones(2)))
    assert shape.value.code == "shape_mismatch"

    with pytest.raises(OptimizationInputError) as non_finite:
        prepare_input(
            _request(
                policy=policy,
                scenario_returns=np.array([[0.0, float("nan")], [0.0, 0.0]]),
            )
        )
    assert non_finite.value.code == "invalid_scenarios"


def test_expected_returns_require_matching_finite_vector() -> None:
    with pytest.raises(OptimizationInputError) as shape:
        prepare_input(_request(expected_returns=(0.1,)))
    assert shape.value.code == "shape_mismatch"

    with pytest.raises(OptimizationInputError) as non_finite:
        prepare_input(_request(expected_returns=(0.1, float("inf"))))
    assert non_finite.value.code == "invalid_expected_returns"


def test_industry_caps_require_matching_industry_evidence() -> None:
    policy = _policy(industry_caps=(("bank", 0.5),))
    with pytest.raises(OptimizationInputError) as missing:
        prepare_input(_request(policy=policy))
    assert missing.value.code == "missing_industries"

    with pytest.raises(OptimizationInputError) as shape:
        prepare_input(_request(policy=policy, industries=("bank",)))
    assert shape.value.code == "shape_mismatch"


def test_expected_returns_and_complete_industry_evidence_are_preserved() -> None:
    prepared = prepare_input(
        _request(
            policy=_policy(industry_caps=(("bank", 0.6), ("tech", 0.6))),
            expected_returns=(0.1, 0.2),
            industries=("bank", "tech"),
        )
    )

    assert prepared.expected is not None
    assert prepared.expected.tolist() == [0.1, 0.2]
    assert prepared.industries == ("bank", "tech")


def test_prepared_subset_requires_unique_in_range_indices() -> None:
    prepared = prepare_input(_request())
    for indices in ((), (0, 0), (-1,), (2,)):
        with pytest.raises(ValueError, match="active-set"):
            subset_prepared_input(prepared, indices)

    subset = subset_prepared_input(prepared, (1,))
    assert subset.indices == (1,)
    assert subset.covariance.shape == (1, 1)
