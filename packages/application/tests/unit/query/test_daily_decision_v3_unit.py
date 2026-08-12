"""Daily Decision V3 typed report composition tests."""

from __future__ import annotations

from dataclasses import replace

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
    build_daily_decision_v3_report,
)


def _v2(status: str = "ready") -> DailyDecisionV2Report:
    return DailyDecisionV2Report(
        identity={
            "strategy_id": "s1",
            "signal_date": "2026-04-01",
            "account_id": "paper-1",
            "sleeve_id": "core",
        },
        readiness={"status": status, "reason_codes": (), "details": ()},
        data={},
        run_package={},
        account_positions={},
        actions=(),
        execution_review={},
    )


def _projection(*, reconciliation_status: str = "reconciled"):
    return DailyDecisionV3Projection(
        portfolio_construction=PortfolioConstructionSection(
            status="optimal",
            mode="mvo",
            policy_digest="policy-digest",
            solver="OSQP",
            solver_version="1.1.3",
            solver_status="optimal",
            duration_ms=12.0,
        ),
        tail_risk=TailRiskSection(
            historical_es99=0.04,
            historical_var99=0.03,
            parametric_var99=0.02,
            monte_carlo_var99=0.025,
            monte_carlo_seed=42,
        ),
        factor_risk=FactorRiskSection(
            availability="partial",
            total_risk=0.1,
            marginal_contributions={"size": 0.2, "specific:1": 0.1},
            percentage_contributions={"size": 0.5, "specific:1": 0.5},
            euler_residual=0.0,
        ),
        stress_tests=StressTestSection(
            catalog_version="r4-v1",
            losses={"hypothetical:market-minus-10pct": 0.1},
        ),
        reconciliation=ReconciliationSection(
            status=reconciliation_status,
            differences=(
                ("risk_position_fingerprint",)
                if reconciliation_status == "mismatch"
                else ()
            ),
            alert_idempotency_key="reconciliation:abc",
        ),
        provenance=ProvenanceSection(
            decision_time="2026-04-01T00:00:00Z",
            knowledge_cutoff="2026-03-31T23:00:00Z",
            publication_cutoff="2026-03-31T23:00:00Z",
            source_snapshot_ids=("snap-1",),
            generated_at="2026-04-01T00:01:00Z",
        ),
    )


def test_v3_preserves_v2_and_exposes_typed_risk_sections() -> None:
    v2 = _v2()

    report = build_daily_decision_v3_report(v2, _projection())

    assert report.v2 is v2
    assert report.readiness == "ready"
    assert report.blocking_reasons == ()
    assert report.tail_risk.historical_es99 >= report.tail_risk.historical_var99
    assert report.factor_risk.availability == "partial"
    assert report.factor_risk.marginal_contributions == {
        "size": 0.2,
        "specific:1": 0.1,
    }


def test_reconciliation_mismatch_forces_v3_blocked_without_mutating_v2() -> None:
    v2 = _v2()

    report = build_daily_decision_v3_report(
        v2,
        _projection(reconciliation_status="mismatch"),
    )

    assert report.readiness == "blocked"
    assert "RECONCILIATION_MISMATCH" in report.blocking_reasons
    assert v2.readiness["status"] == "ready"


def test_missing_v3_projection_fails_closed() -> None:
    report = build_daily_decision_v3_report(_v2(), None)

    assert report.readiness == "blocked"
    assert report.blocking_reasons == ("R4_RISK_REPORT_MISSING",)
    assert report.portfolio_construction.status == "unavailable"


def test_incomplete_or_non_optimal_persisted_evidence_fails_closed() -> None:
    projection = _projection()
    projection = replace(
        projection,
        portfolio_construction=replace(
            projection.portfolio_construction,
            solver_status="optimal_inaccurate",
        ),
        tail_risk=replace(projection.tail_risk, historical_es99=None),
        provenance=replace(projection.provenance, source_snapshot_ids=()),
    )

    report = build_daily_decision_v3_report(_v2(), projection)

    assert report.readiness == "blocked"
    assert "PORTFOLIO_CONSTRUCTION_EVIDENCE_INVALID" in report.blocking_reasons
    assert "TAIL_RISK_INCOMPLETE" in report.blocking_reasons
    assert "PROVENANCE_INCOMPLETE" in report.blocking_reasons


def test_v3_reader_uses_identity_resolved_by_v2() -> None:
    calls: list[dict[str, str | None]] = []

    class _V2Facade:
        def get_report_v2(self, **_kwargs: object) -> DailyDecisionV2Report:
            return _v2()

    class _ProjectionReader:
        def get_latest(
            self,
            *,
            strategy_id: str,
            trade_date: str | None,
            account_id: str | None,
            sleeve_id: str | None,
        ) -> DailyDecisionV3Projection | None:
            calls.append(
                {
                    "strategy_id": strategy_id,
                    "trade_date": trade_date,
                    "account_id": account_id,
                    "sleeve_id": sleeve_id,
                }
            )
            return _projection()

    report = DailyDecisionV3QueryFacade(
        v2_facade=_V2Facade(),
        projection_reader=_ProjectionReader(),
    ).get_report_v3(strategy_id="s1")

    assert report.readiness == "ready"
    assert calls == [
        {
            "strategy_id": "s1",
            "trade_date": "2026-04-01",
            "account_id": "paper-1",
            "sleeve_id": "core",
        }
    ]
