"""Derived benchmark harness tests."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest


def _load_benchmark_module() -> ModuleType:
    module_path = (
        Path(__file__).resolve().parents[4]
        / "scripts"
        / "benchmarks"
        / "derived_benchmark.py"
    )
    spec = importlib.util.spec_from_file_location("derived_benchmark", module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_default_workloads_cover_phase6_targets() -> None:
    module = _load_benchmark_module()

    workloads = module.default_workloads()

    assert [workload.name for workload in workloads] == [
        "query",
        "materialize",
        "shadow_compare",
    ]
    assert {scale.name for workload in workloads for scale in workload.scales} == {
        "S",
        "M",
        "L",
    }


@pytest.mark.parametrize(
    ("elapsed_seconds", "baseline_seconds", "expected"),
    [
        (1.10, 1.00, "pass"),
        (1.20, 1.00, "warning"),
        (1.30, 1.00, "error"),
    ],
)
def test_regression_budget_uses_phase1_thresholds(
    elapsed_seconds: float,
    baseline_seconds: float,
    expected: str,
) -> None:
    module = _load_benchmark_module()

    budget = module.RegressionBudget()

    assert (
        budget.classify(
            elapsed_seconds=elapsed_seconds,
            baseline_seconds=baseline_seconds,
        )
        == expected
    )


@pytest.mark.slow
def test_run_benchmark_suite_returns_positive_measurements_for_s_scale() -> None:
    module = _load_benchmark_module()

    results = module.run_benchmark_suite(scales=("S",), iterations=1)

    assert [result.workload for result in results] == [
        "query",
        "materialize",
        "shadow_compare",
    ]
    assert {result.scale for result in results} == {"S"}
    for result in results:
        assert result.row_count > 0
        assert result.elapsed_seconds > 0
        assert result.throughput_rows_per_second > 0
