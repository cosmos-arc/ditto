"""Tests for minimum launch risk report construction."""

from __future__ import annotations

import pytest
from ditto_risk.models import RiskPosition, StressScenario, build_launch_risk_report


def test_launch_risk_report_includes_minimum_required_metrics() -> None:
    report = build_launch_risk_report(
        positions=(
            RiskPosition(instrument_id=1, weight=0.40, industry="technology"),
            RiskPosition(instrument_id=2, weight=0.35, industry="finance"),
            RiskPosition(instrument_id=3, weight=0.25, industry="technology"),
        ),
        benchmark_weights={1: 0.30, 2: 0.30, 4: 0.40},
        nav_series=(
            ("2026-06-17", 100.0),
            ("2026-06-18", 110.0),
            ("2026-06-19", 104.5),
            ("2026-06-20", 99.275),
            ("2026-06-21", 101.2605),
        ),
        stress_scenarios=(
            StressScenario(name="market_down", market_shock=-0.10),
            StressScenario(
                name="sector_down",
                industry_shocks={"technology": -0.20},
            ),
        ),
    )

    assert report.concentration.max_weight == pytest.approx(0.40)
    assert report.concentration.top_5_weight == pytest.approx(1.0)
    assert report.concentration.herfindahl_index == pytest.approx(0.345)
    assert report.industry_exposure == {
        "finance": pytest.approx(0.35),
        "technology": pytest.approx(0.65),
    }
    assert report.benchmark_active_weight.active_weights == {
        "1": pytest.approx(0.10),
        "2": pytest.approx(0.05),
        "3": pytest.approx(0.25),
        "4": pytest.approx(-0.40),
    }
    assert report.benchmark_active_weight.total_abs_active_weight == pytest.approx(
        0.80,
    )
    assert report.drawdown.max_drawdown == pytest.approx(-0.0975)
    assert report.tail_risk.var_95 == pytest.approx(-0.05)
    assert report.tail_risk.cvar_95 == pytest.approx(-0.05)
    assert report.stress_scenario_returns == {
        "market_down": pytest.approx(-0.10),
        "sector_down": pytest.approx(-0.13),
    }


def test_launch_risk_report_serializes_to_stable_dict_contract() -> None:
    report = build_launch_risk_report(
        positions=(RiskPosition(instrument_id=1, weight=1.0, industry=None),),
        benchmark_weights={1: 0.75},
        nav_series=(("2026-06-20", 100.0), ("2026-06-21", 90.0)),
        stress_scenarios=(StressScenario(name="market_down", market_shock=-0.10),),
    )

    payload = report.to_dict()

    assert payload["concentration"]["max_weight"] == pytest.approx(1.0)
    assert payload["industry_exposure"] == {"unclassified": pytest.approx(1.0)}
    assert payload["benchmark_active_weight"]["active_weights"] == {
        "1": pytest.approx(0.25),
    }
    assert payload["drawdown"]["max_drawdown"] == pytest.approx(-0.10)
    assert payload["tail_risk"]["var_95"] == pytest.approx(-0.10)
    assert payload["stress_scenario_returns"]["market_down"] == pytest.approx(-0.10)
