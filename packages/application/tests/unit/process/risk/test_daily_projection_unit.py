"""Daily Decision V3 projection production and persistence tests."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import Mock

from ditto_application.processes.portfolio.construction import (
    PortfolioConstructionDecision,
)
from ditto_application.processes.risk.daily_projection import (
    DailyRiskProjectionInput,
    DailyRiskProjectionProcess,
)
from ditto_application.processes.risk.persistence import RiskPersistencePort
from ditto_application.processes.risk.reconciliation import ReconciliationReport
from ditto_risk.analytics import StressTestReport, TailRiskReport


def _input(*, mismatch: bool = False, requires_stock_factor_risk: bool = False):
    return DailyRiskProjectionInput(
        strategy_id="s1",
        account_id="paper-1",
        sleeve_id="core",
        trade_date="2026-04-01",
        portfolio_construction=PortfolioConstructionDecision(
            success=True,
            target=None,
            evidence={
                "mode": "enforced",
                "policy_digest": "policy-1",
                "solver": "OSQP",
                "solver_version": "1.1.3",
                "solver_status": "optimal",
            },
        ),
        portfolio_duration_ms=12.0,
        tail_risk=TailRiskReport(
            confidence_level=0.99,
            observation_count=250,
            historical_var=0.03,
            historical_es=0.04,
            parametric_var=0.02,
            monte_carlo_var=0.025,
            monte_carlo_seed=42,
        ),
        factor_risk=None,
        requires_stock_factor_risk=requires_stock_factor_risk,
        stress_tests=StressTestReport(
            catalog_version="r4-v1",
            losses={"hypothetical:market-minus-10pct": 0.10},
        ),
        reconciliation=ReconciliationReport(
            account_id="paper-1",
            sleeve_id="core",
            trade_date="2026-04-01",
            status="mismatch" if mismatch else "reconciled",
            differences=("risk_position_fingerprint",) if mismatch else (),
            suggestion_allowed=not mismatch,
            alert_idempotency_key="reconciliation:key" if mismatch else None,
        ),
        decision_time=datetime(2026, 4, 1, tzinfo=UTC),
        knowledge_cutoff=datetime(2026, 3, 31, 23, tzinfo=UTC),
        publication_cutoff=datetime(2026, 3, 31, 23, tzinfo=UTC),
        source_snapshot_ids=("snap-1",),
        generated_at=datetime(2026, 4, 1, 1, tzinfo=UTC),
    )


def test_projection_persists_blocked_report_and_sends_idempotent_alert() -> None:
    persistence = Mock(spec=RiskPersistencePort)
    alert_port = Mock()
    process = DailyRiskProjectionProcess(
        persistence=persistence,
        reconciliation_alert=alert_port,
    )

    projection = process.build_and_persist(_input(mismatch=True))

    assert "RECONCILIATION_MISMATCH" in projection.blocking_reasons
    record = persistence.append_daily_report.call_args.args[0]
    assert record.projection is projection
    assert record.report_id.startswith("r4-v3:")
    alert_port.send.assert_called_once()
    assert alert_port.send.call_args.args[0].alert_idempotency_key == (
        "reconciliation:key"
    )


def test_stock_portfolio_without_factor_result_is_blocked() -> None:
    persistence = Mock(spec=RiskPersistencePort)
    process = DailyRiskProjectionProcess(persistence=persistence)

    projection = process.build_and_persist(_input(requires_stock_factor_risk=True))

    assert projection.factor_risk.availability == "unavailable"
    assert "STOCK_FACTOR_RISK_UNAVAILABLE" in projection.blocking_reasons
