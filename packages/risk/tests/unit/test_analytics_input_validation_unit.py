"""Fail-closed validation for tail-risk and stress-test inputs."""

from __future__ import annotations

from dataclasses import replace

import pytest
from ditto_risk.analytics import (
    R4_STRESS_CATALOG,
    StressTestInput,
    compute_stress_tests,
    compute_tail_risk,
)


def _stress_input() -> StressTestInput:
    historical = {
        scenario.scenario_id: (-0.01, 0.01)
        for scenario in R4_STRESS_CATALOG.scenarios
        if scenario.kind == "historical"
    }
    return StressTestInput(
        historical_returns=historical,
        market_exposure=0.8,
        industry_weights={"technology": 0.4},
        base_liquidity_cost=0.01,
        style_one_sigma_losses={"value": 0.02},
    )


def test_stress_input_rejects_missing_and_invalid_historical_windows() -> None:
    value = _stress_input()
    first = next(iter(value.historical_returns))
    missing = dict(value.historical_returns)
    missing.pop(first)
    with pytest.raises(ValueError, match="returns missing"):
        compute_stress_tests(replace(value, historical_returns=missing))

    invalid = dict(value.historical_returns)
    invalid[first] = (-1.0,)
    with pytest.raises(ValueError, match="returns invalid"):
        compute_stress_tests(replace(value, historical_returns=invalid))


@pytest.mark.parametrize(
    ("changes", "match"),
    [
        ({"market_exposure": float("nan")}, "market_exposure"),
        ({"market_exposure": -0.1}, "market_exposure"),
        ({"base_liquidity_cost": float("inf")}, "base_liquidity_cost"),
        ({"base_liquidity_cost": -0.1}, "base_liquidity_cost"),
        ({"industry_weights": {"": 0.1}}, "industry weights"),
        ({"industry_weights": {"technology": -0.1}}, "industry weights"),
        ({"style_one_sigma_losses": {"": 0.1}}, "style stress"),
        ({"style_one_sigma_losses": {"value": float("nan")}}, "style stress"),
    ],
)
def test_stress_input_requires_finite_nonnegative_named_exposures(
    changes: dict[str, object],
    match: str,
) -> None:
    with pytest.raises(ValueError, match=match):
        compute_stress_tests(replace(_stress_input(), **changes))


def test_style_scenario_is_explicitly_unavailable_without_style_evidence() -> None:
    report = compute_stress_tests(replace(_stress_input(), style_one_sigma_losses=None))
    assert report.unavailable_scenarios == (
        "hypothetical:style-factor-plus-minus-3sigma",
    )


def test_complete_style_evidence_produces_a_deterministic_positive_loss() -> None:
    report = compute_stress_tests(_stress_input())

    assert report.losses[
        "hypothetical:style-factor-plus-minus-3sigma"
    ] == pytest.approx(0.06)
    assert report.unavailable_scenarios == ()


@pytest.mark.parametrize(
    ("confidence", "samples", "match"),
    [
        (0.0, 100, "confidence_level"),
        (1.0, 100, "confidence_level"),
        (0.99, 99, "samples"),
    ],
)
def test_tail_risk_rejects_invalid_confidence_or_sample_budget(
    confidence: float,
    samples: int,
    match: str,
) -> None:
    with pytest.raises(ValueError, match=match):
        compute_tail_risk(
            tuple(0.001 for _ in range(60)),
            confidence_level=confidence,
            monte_carlo_samples=samples,
        )
