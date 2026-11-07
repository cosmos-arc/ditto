"""Performance harness over real deterministic workstation callbacks."""

from __future__ import annotations

import sqlite3
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
    assert all(
        item.threshold_ms is not None and item.p95_ms <= item.threshold_ms
        for item in report.cases
    )
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


def test_unbudgeted_storage_read_reports_measurement_without_claiming_slo(
    tmp_path: Path,
) -> None:
    with sqlite3.connect(tmp_path / "read-model.sqlite") as db:
        db.execute("CREATE TABLE positions (quantity INTEGER)")
        db.execute("INSERT INTO positions VALUES (100)")

        def read_position() -> object:
            row = db.execute("SELECT quantity FROM positions").fetchone()
            assert row == (100,)
            return row

        ticks = iter((0, 2_000_000, 2_000_000, 6_000_000))
        report = benchmark_workstation(
            (PerformanceCase("stored_position", read_position, threshold_ms=None),),
            warmup=5,
            iterations=2,
            clock_ns=lambda: next(ticks),
        )
    result = report.cases[0]
    assert (result.median_ms, result.p95_ms, result.max_ms) == (3.0, 4.0, 4.0)
    assert result.threshold_ms is None
    assert result.status == report.status == "measured"


def test_exceeded_budget_retains_complete_report(tmp_path: Path) -> None:
    ticks = iter((0, 2_000_000, 2_000_000, 6_000_000))
    with pytest.raises(PerformanceBudgetError) as failure:
        benchmark_workstation(
            (PerformanceCase("slow", lambda: None, threshold_ms=1.0),),
            warmup=0,
            iterations=2,
            clock_ns=lambda: next(ticks),
        )
    report = failure.value.report
    write_performance_report(tmp_path / "failed.json", report)
    assert report.status == "failed"
    assert report.cases[0].p95_ms == 4.0
    assert orjson.loads((tmp_path / "failed.json").read_bytes())["status"] == "failed"
