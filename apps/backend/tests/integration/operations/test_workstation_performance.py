"""Performance harness over real deterministic workstation callbacks."""

from __future__ import annotations

from pathlib import Path

import orjson
import pytest
from ditto_apps.operations.workstation_performance import (
    PerformanceBudgetError,
    PerformanceCase,
    benchmark_workstation,
    write_performance_report,
)
from ditto_apps.registry.performance_probes import (
    default_workstation_performance_cases,
)


def test_default_workstation_cases_emit_p95_for_every_required_path(
    tmp_path: Path,
) -> None:
    report = benchmark_workstation(
        default_workstation_performance_cases(),
        warmup=1,
        iterations=5,
    )
    destination = tmp_path / "performance.json"
    write_performance_report(destination, report)

    persisted = orjson.loads(destination.read_bytes())
    assert report.status == "passed"
    assert {item.name for item in report.cases} == {
        "read_models",
        "selection",
        "technical_analysis",
        "portfolio_comparison",
    }
    assert all(item.p95_ms <= item.threshold_ms for item in report.cases)
    assert persisted["report_hash"] == report.report_hash


def test_performance_budget_fails_closed() -> None:
    ticks = iter((0, 2_000_000, 2_000_000, 4_000_000))

    with pytest.raises(PerformanceBudgetError, match="slow"):
        benchmark_workstation(
            (PerformanceCase("slow", lambda: None, threshold_ms=1.0),),
            warmup=0,
            iterations=2,
            clock_ns=lambda: next(ticks),
        )
