"""Contract tests for exact DailyDecision V3 evidence reads."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal, cast
from unittest.mock import MagicMock

import pytest
from ditto_application.exceptions import AppQueryError
from ditto_application.providers_portfolio import AppPortfolioQueryProvider
from ditto_application.queries.daily_decision import DailyDecisionV2Report
from ditto_application.queries.daily_decision_v3 import (
    DailyDecisionV3QueryFacade,
    DailyDecisionV3Report,
    FactorRiskSection,
    PortfolioConstructionSection,
    ProvenanceSection,
    ReconciliationSection,
    StressTestSection,
    TailRiskSection,
)
from ditto_application.queries.decision_evidence import (
    DecisionEvidenceQueryFacade,
    EvidenceTemporalContext,
)


def _context() -> EvidenceTemporalContext:
    return EvidenceTemporalContext(
        decision_time=datetime(2026, 8, 16, 8, tzinfo=UTC),
        knowledge_cutoff=datetime(2026, 8, 16, 7, tzinfo=UTC),
        publication_cutoff=datetime(2026, 8, 16, 6, tzinfo=UTC),
        source_snapshot_id="snapshot-1",
    )


def _report(
    *,
    readiness: Literal["ready", "blocked", "review"] = "ready",
    snapshot_id: str = "snapshot-1",
) -> DailyDecisionV3Report:
    return DailyDecisionV3Report(
        v2=DailyDecisionV2Report(
            identity={
                "strategy_id": "strategy-1",
                "strategy_version": "3",
                "signal_date": "2026-08-15",
                "account_id": "account-1",
                "sleeve_id": "sleeve-1",
            },
            readiness={"status": "ready"},
            data={},
            run_package={},
            account_positions={"positions": [{"instrument_id": 510300}]},
            actions=(),
            execution_review={},
        ),
        readiness=readiness,
        blocking_reasons=(() if readiness == "ready" else ("RISK_BLOCKED",)),
        portfolio_construction=PortfolioConstructionSection(
            status="optimal",
            policy_digest="policy-1",
            solver="OSQP",
            solver_version="1.0",
            solver_status="optimal",
            duration_ms=1.0,
        ),
        tail_risk=TailRiskSection(0.03, 0.02, 0.02, 0.02, 7),
        factor_risk=FactorRiskSection(
            "available",
            0.2,
            {"market": 0.2},
            {"market": 1.0},
            0.0,
        ),
        stress_tests=StressTestSection("v1", {"market_down": 0.1}),
        reconciliation=ReconciliationSection("reconciled", (), None),
        provenance=ProvenanceSection(
            decision_time="2026-08-16T08:00:00Z",
            knowledge_cutoff="2026-08-16T07:00:00Z",
            publication_cutoff="2026-08-16T06:00:00Z",
            source_snapshot_ids=(snapshot_id,),
            generated_at="2026-08-16T08:00:01Z",
        ),
    )


def _facade(
    report: DailyDecisionV3Report,
) -> tuple[DecisionEvidenceQueryFacade, MagicMock]:
    v3 = MagicMock(spec=DailyDecisionV3QueryFacade)
    v3.get_report_v3.return_value = report
    return (
        DecisionEvidenceQueryFacade(
            daily_decision_v3=cast(DailyDecisionV3QueryFacade, v3)
        ),
        v3,
    )


def test_decision_facade_binds_portfolio_risk_and_v3_to_exact_identity() -> None:
    facade, v3 = _facade(_report())

    result = facade.get_evidence(
        strategy_id="strategy-1",
        strategy_version="3",
        trade_date="2026-08-15",
        account_id="account-1",
        sleeve_id="sleeve-1",
        context=_context(),
    )

    assert result.strategy_id == "strategy-1"
    assert result.readiness == "ready"
    assert result.payload.value["portfolio_construction"]["status"] == "optimal"
    assert result.payload.value["tail_risk"]["historical_es99"] == 0.03
    assert result.payload.value["factor_risk"]["availability"] == "available"
    assert result.payload.value["v2"]["account_positions"]["positions"]
    assert result.artifact_refs[0].content_hash == result.payload.payload_hash
    v3.get_report_v3.assert_called_once_with(
        strategy_id="strategy-1",
        trade_date="2026-08-15",
        account_id="account-1",
    )


@pytest.mark.parametrize(
    ("report", "expected_code"),
    [
        (_report(readiness="blocked"), "DECISION_EVIDENCE_NOT_READY"),
        (_report(snapshot_id="wrong"), "EVIDENCE_SNAPSHOT_MISMATCH"),
    ],
)
def test_decision_facade_fails_closed_on_readiness_or_snapshot(
    report: DailyDecisionV3Report,
    expected_code: str,
) -> None:
    facade, _ = _facade(report)

    with pytest.raises(AppQueryError) as exc_info:
        facade.get_evidence(
            strategy_id="strategy-1",
            strategy_version="3",
            trade_date="2026-08-15",
            account_id="account-1",
            sleeve_id="sleeve-1",
            context=_context(),
        )

    assert exc_info.value.details["code"] == expected_code


def test_decision_facade_rejects_missing_identity_before_provider_call() -> None:
    facade, v3 = _facade(_report())

    with pytest.raises(AppQueryError) as exc_info:
        facade.get_evidence(
            strategy_id="strategy-1",
            strategy_version="3",
            trade_date="",
            account_id="account-1",
            sleeve_id="sleeve-1",
            context=_context(),
        )

    assert exc_info.value.details["code"] == "EVIDENCE_IDENTITY_REQUIRED"
    v3.get_report_v3.assert_not_called()


def test_portfolio_provider_wires_decision_evidence_facade() -> None:
    _, v3 = _facade(_report())
    provider = AppPortfolioQueryProvider()

    wired = provider.decision_evidence_query_facade(
        daily_decision_v3=cast(DailyDecisionV3QueryFacade, v3)
    )

    assert isinstance(wired, DecisionEvidenceQueryFacade)
