"""R4 benchmark harness smoke tests."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType


def _load_module() -> ModuleType:
    path = (
        Path(__file__).resolve().parents[5]
        / "scripts"
        / "benchmarks"
        / "r4_portfolio_risk.py"
    )
    spec = importlib.util.spec_from_file_location("r4_portfolio_risk", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load R4 benchmark harness")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_fixed_optimizer_scales_and_smoke_measurement() -> None:
    module = _load_module()

    assert module.OPTIMIZER_SCALES == (50, 200, 500)
    result = module.run_optimizer_benchmarks(scales=(50,), iterations=1)

    assert result[0].workload == "mvo"
    assert result[0].scale == 50
    assert result[0].p95_seconds > 0.0
    assert result[0].limit_seconds == 5.0

    eod = module.run_eod_risk_reconciliation_benchmark(scale=50, iterations=1)
    v3 = module.run_v3_query_benchmark(iterations=1)

    assert eod.workload == "eod_risk_reconciliation"
    assert eod.limit_seconds == 60.0
    assert v3.workload == "daily_decision_v3_query"
    assert v3.limit_seconds == 2.0
