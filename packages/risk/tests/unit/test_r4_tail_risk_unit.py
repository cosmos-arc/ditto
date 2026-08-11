"""R4 positive-loss tail risk and stress catalog tests."""

from __future__ import annotations

import pytest
from ditto_risk.analytics import (
    R4_STRESS_CATALOG,
    StressTestInput,
    compute_stress_tests,
    compute_tail_risk,
)


def test_historical_es99_uses_positive_loss_and_dominates_var() -> None:
    returns = (-0.20, -0.10, *([-0.01] * 98))

    report = compute_tail_risk(returns, confidence_level=0.99, monte_carlo_seed=7)

    assert report.historical_var == pytest.approx(0.20)
    assert report.historical_es == pytest.approx(0.20)
    assert report.historical_es >= report.historical_var
    assert report.loss_sign_convention == "positive_loss"


def test_monte_carlo_diagnostic_is_deterministic_for_fixed_seed() -> None:
    returns = tuple((offset % 11 - 5) / 100 for offset in range(100))

    first = compute_tail_risk(returns, monte_carlo_seed=42)
    second = compute_tail_risk(returns, monte_carlo_seed=42)

    assert first.monte_carlo_var == second.monte_carlo_var
    assert first.monte_carlo_seed == 42


def test_tail_risk_rejects_insufficient_or_non_finite_evidence() -> None:
    with pytest.raises(ValueError, match="at least 60"):
        compute_tail_risk(tuple([-0.01] * 59))
    with pytest.raises(ValueError, match="finite"):
        compute_tail_risk(tuple([-0.01] * 59 + [float("nan")]))


def test_r4_stress_catalog_has_historical_and_hypothetical_cases() -> None:
    identifiers = {scenario.scenario_id for scenario in R4_STRESS_CATALOG.scenarios}

    assert R4_STRESS_CATALOG.version == "r4-v1"
    assert "historical:2015-equity-crash" in identifiers
    assert "historical:2020-covid" in identifiers
    assert "historical:2024-small-cap-liquidity" in identifiers
    assert "hypothetical:market-minus-10pct" in identifiers
    assert "hypothetical:largest-industry-minus-20pct" in identifiers
    assert "hypothetical:liquidity-cost-x2" in identifiers
    assert "hypothetical:style-factor-plus-minus-3sigma" in identifiers


def test_stress_engine_computes_versioned_positive_losses_without_fake_style() -> None:
    report = compute_stress_tests(
        StressTestInput(
            historical_returns={
                "historical:2015-equity-crash": (-0.10, -0.10),
                "historical:2020-covid": (-0.05,),
                "historical:2024-small-cap-liquidity": (0.02,),
            },
            market_exposure=0.8,
            industry_weights={"bank": 0.4, "technology": 0.3},
            base_liquidity_cost=0.01,
            style_one_sigma_losses=None,
        )
    )

    assert report.catalog_version == "r4-v1"
    assert report.losses["historical:2015-equity-crash"] == pytest.approx(0.19)
    assert report.losses["hypothetical:market-minus-10pct"] == pytest.approx(0.08)
    assert report.losses["hypothetical:largest-industry-minus-20pct"] == pytest.approx(
        0.08
    )
    assert report.losses["hypothetical:liquidity-cost-x2"] == pytest.approx(0.02)
    assert report.unavailable_scenarios == (
        "hypothetical:style-factor-plus-minus-3sigma",
    )


def test_stress_engine_requires_all_historical_windows() -> None:
    with pytest.raises(ValueError, match="historical:2020-covid"):
        compute_stress_tests(
            StressTestInput(
                historical_returns={
                    "historical:2015-equity-crash": (-0.10,),
                    "historical:2024-small-cap-liquidity": (-0.02,),
                },
                market_exposure=1.0,
                industry_weights={"bank": 1.0},
                base_liquidity_cost=0.01,
                style_one_sigma_losses={"size": 0.01},
            )
        )
