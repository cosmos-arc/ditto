"""Exact benchmark identity behavior for the launch risk report."""

from __future__ import annotations

from ditto_risk.models import RiskPosition, build_launch_risk_report


def test_equal_benchmark_weight_is_omitted_from_active_exposure() -> None:
    report = build_launch_risk_report(
        positions=(RiskPosition(instrument_id=600519, weight=1.0),),
        benchmark_weights={600519: 1.0},
    )

    assert report.benchmark_active_weight.active_weights == {}
    assert report.benchmark_active_weight.total_abs_active_weight == 0.0
