#!/usr/bin/env python3
"""Deterministic R4 optimizer and in-memory RiskGate SLO benchmark."""

from __future__ import annotations

import argparse
import statistics
import time
from dataclasses import asdict, dataclass

import numpy as np
import orjson
from ditto_application.processes.risk.reconciliation import (
    PlannedOrder,
    ReconciliationFill,
    ReconciliationInput,
    reconcile_eod,
)
from ditto_application.queries.daily_decision import DailyDecisionV2Report
from ditto_application.queries.daily_decision_v3 import (
    DailyDecisionV3Projection,
    DailyDecisionV3QueryFacade,
    FactorRiskSection,
    PortfolioConstructionSection,
    ProvenanceSection,
    ReconciliationSection,
    StressTestSection,
    TailRiskSection,
)
from ditto_execution.orders.ids import ClientOrderId
from ditto_execution.orders.model import Order
from ditto_kernel.order import OrderSide, OrderType
from ditto_portfolio.accounting import Account, CashBook
from ditto_portfolio.rebalancing.optimization_models import (
    OptimizationMethod,
    PortfolioConstructionPolicy,
    PortfolioOptimizationRequest,
)
from ditto_portfolio.rebalancing.optimizer import CVXPYPortfolioOptimizer
from ditto_risk.analytics import compute_tail_risk
from ditto_risk.continuous_gate import (
    ContinuousRiskGate,
    DailyRiskInput,
    RiskGateContext,
)

OPTIMIZER_SCALES = (50, 200, 500)
OPTIMIZER_P95_LIMIT_SECONDS = 5.0
PRE_TRADE_P95_LIMIT_SECONDS = 0.05
EOD_P95_LIMIT_SECONDS = 60.0
V3_QUERY_P95_LIMIT_SECONDS = 2.0


@dataclass(frozen=True)
class SloMeasurement:
    """One p95 SLO measurement with an explicit pass/fail threshold."""

    workload: str
    scale: int
    iterations: int
    p95_seconds: float
    limit_seconds: float
    passed: bool


def run_optimizer_benchmarks(
    *,
    scales: tuple[int, ...] = OPTIMIZER_SCALES,
    iterations: int = 5,
) -> tuple[SloMeasurement, ...]:
    """Measure deterministic minimum-variance construction at fixed scales."""
    optimizer = CVXPYPortfolioOptimizer()
    measurements: list[SloMeasurement] = []
    for count in scales:
        request = _optimizer_request(count)
        optimizer.optimize(request)
        samples: list[float] = []
        for _ in range(iterations):
            started = time.perf_counter()
            result = optimizer.optimize(request)
            samples.append(time.perf_counter() - started)
            if not result.success:
                raise RuntimeError(f"optimizer benchmark failed: {result.failure_code}")
        p95 = _p95(samples)
        measurements.append(
            SloMeasurement(
                workload="mvo",
                scale=count,
                iterations=iterations,
                p95_seconds=p95,
                limit_seconds=OPTIMIZER_P95_LIMIT_SECONDS,
                passed=p95 <= OPTIMIZER_P95_LIMIT_SECONDS,
            )
        )
    return tuple(measurements)


def run_pre_trade_benchmark(*, iterations: int = 2_000) -> SloMeasurement:
    """Measure the pure in-memory continuous pre-trade gate."""
    gate = ContinuousRiskGate(account_id="benchmark", sleeve_id="core")
    account = Account(
        cash=CashBook(available=1_000_000.0, settled=1_000_000.0, frozen=0.0)
    ).get_view()
    context = RiskGateContext(
        account_id="benchmark",
        sleeve_id="core",
        trade_date="2026-08-10",
        account_view=account,
        position_fingerprint="benchmark-empty",
    )
    order = Order(
        client_id=ClientOrderId("benchmark-order"),
        instrument_id=1,
        order_type=OrderType.LIMIT,
        direction=OrderSide.BUY,
        quantity=100,
        price=10.0,
        trade_date="2026-08-10",
    )
    samples: list[float] = []
    for _ in range(iterations):
        started = time.perf_counter()
        gate.pre_trade(order, context)
        samples.append(time.perf_counter() - started)
    p95 = _p95(samples)
    return SloMeasurement(
        workload="pre_trade_risk_gate",
        scale=1,
        iterations=iterations,
        p95_seconds=p95,
        limit_seconds=PRE_TRADE_P95_LIMIT_SECONDS,
        passed=p95 <= PRE_TRADE_P95_LIMIT_SECONDS,
    )


def run_eod_risk_reconciliation_benchmark(
    *,
    scale: int = 500,
    iterations: int = 5,
) -> SloMeasurement:
    """Measure a single-account risk scan, tail calculation, and reconciliation."""
    account = Account(
        cash=CashBook(available=1_000_000.0, settled=1_000_000.0, frozen=0.0)
    ).get_view()
    gate = ContinuousRiskGate(account_id="benchmark", sleeve_id="core")
    context = RiskGateContext(
        account_id="benchmark",
        sleeve_id="core",
        trade_date="2026-08-10",
        account_view=account,
        position_fingerprint="benchmark-empty",
    )
    reconciliation_input = ReconciliationInput(
        account_id="benchmark",
        sleeve_id="core",
        trade_date="2026-08-10",
        planned_orders=tuple(
            PlannedOrder(f"order-{index}", index, "buy", 100)
            for index in range(1, scale + 1)
        ),
        fills=tuple(
            ReconciliationFill(
                f"fill-{index}",
                f"order-{index}",
                index,
                "buy",
                100,
            )
            for index in range(1, scale + 1)
        ),
        opening_positions={},
        actual_positions=dict.fromkeys(range(1, scale + 1), 100),
        risk_position_fingerprint="sha256:benchmark-positions",
        actual_position_fingerprint="sha256:benchmark-positions",
    )
    returns = tuple((index % 17 - 8) / 1_000 for index in range(250))
    samples: list[float] = []
    for _ in range(iterations):
        started = time.perf_counter()
        risk_report = gate.daily_scan(DailyRiskInput(context=context, nav=account.nav))
        tail_report = compute_tail_risk(returns, monte_carlo_samples=1_000)
        reconciliation = reconcile_eod(reconciliation_input)
        samples.append(time.perf_counter() - started)
        if risk_report.readiness != "ready" or reconciliation.status != "reconciled":
            raise RuntimeError("EOD risk/reconciliation benchmark failed")
        if tail_report.historical_es < tail_report.historical_var:
            raise RuntimeError("tail-risk benchmark violated ES/VaR")
    p95 = _p95(samples)
    return SloMeasurement(
        workload="eod_risk_reconciliation",
        scale=scale,
        iterations=iterations,
        p95_seconds=p95,
        limit_seconds=EOD_P95_LIMIT_SECONDS,
        passed=p95 <= EOD_P95_LIMIT_SECONDS,
    )


def run_v3_query_benchmark(*, iterations: int = 100) -> SloMeasurement:
    """Measure typed V3 composition over in-memory read providers."""
    v2 = DailyDecisionV2Report(
        identity={"strategy_id": "benchmark"},
        readiness={"status": "ready"},
        data={},
        run_package={},
        account_positions={},
        actions=(),
        execution_review={},
    )
    projection = DailyDecisionV3Projection(
        portfolio_construction=PortfolioConstructionSection(
            status="optimal",
            policy_digest="benchmark-policy",
            solver="OSQP",
            solver_version="1.1.3",
            solver_status="optimal",
            duration_ms=1.0,
        ),
        tail_risk=TailRiskSection(0.04, 0.03, 0.02, 0.025, 42),
        factor_risk=FactorRiskSection("unavailable", None, {}, {}, None),
        stress_tests=StressTestSection("r4-v1", {"benchmark": 0.1}),
        reconciliation=ReconciliationSection("reconciled", (), None),
        provenance=ProvenanceSection(
            "2026-08-10T09:30:00+08:00",
            "2026-08-10T09:29:00+08:00",
            "2026-08-10T09:29:00+08:00",
            ("benchmark-snapshot",),
            "2026-08-10T09:31:00+08:00",
        ),
    )

    class _V2Facade:
        def get_report_v2(self, **kwargs: object) -> DailyDecisionV2Report:
            return v2

    class _ProjectionReader:
        def get_latest(self, **kwargs: object) -> DailyDecisionV3Projection:
            return projection

    facade = DailyDecisionV3QueryFacade(
        v2_facade=_V2Facade(),
        projection_reader=_ProjectionReader(),
    )
    samples: list[float] = []
    for _ in range(iterations):
        started = time.perf_counter()
        report = facade.get_report_v3(strategy_id="benchmark")
        samples.append(time.perf_counter() - started)
        if report.readiness != "ready":
            raise RuntimeError("V3 query benchmark failed")
    p95 = _p95(samples)
    return SloMeasurement(
        workload="daily_decision_v3_query",
        scale=1,
        iterations=iterations,
        p95_seconds=p95,
        limit_seconds=V3_QUERY_P95_LIMIT_SECONDS,
        passed=p95 <= V3_QUERY_P95_LIMIT_SECONDS,
    )


def _optimizer_request(count: int) -> PortfolioOptimizationRequest:
    diagonal = np.linspace(0.01, 0.04, count)
    covariance = np.diag(diagonal) + np.full((count, count), 0.0001)
    equal_weight = 1.0 / count
    return PortfolioOptimizationRequest(
        policy=PortfolioConstructionPolicy(
            policy_id=f"r4-benchmark-{count}",
            version=1,
            method=OptimizationMethod.MVO,
            turnover_penalty_bps=0.0,
            max_weight=max(0.05, equal_weight * 2.0),
            solver_timeout_seconds=5.0,
        ),
        instrument_ids=tuple(range(1, count + 1)),
        covariance=covariance,
        scenario_returns=None,
        candidate_weights=tuple(equal_weight for _ in range(count)),
        current_weights=tuple(equal_weight for _ in range(count)),
        source_snapshot_ids=("benchmark-snapshot",),
    )


def _p95(samples: list[float]) -> float:
    if len(samples) == 1:
        return samples[0]
    return statistics.quantiles(samples, n=100, method="inclusive")[94]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--iterations", type=int, default=5)
    parser.add_argument("--risk-iterations", type=int, default=2_000)
    args = parser.parse_args()
    measurements = (
        *run_optimizer_benchmarks(iterations=args.iterations),
        run_pre_trade_benchmark(iterations=args.risk_iterations),
        run_eod_risk_reconciliation_benchmark(iterations=args.iterations),
        run_v3_query_benchmark(iterations=args.risk_iterations),
    )
    print(
        orjson.dumps(
            [asdict(item) for item in measurements],
            option=orjson.OPT_INDENT_2 | orjson.OPT_SORT_KEYS,
        ).decode()
    )
    return 0 if all(item.passed for item in measurements) else 1


if __name__ == "__main__":
    raise SystemExit(main())
