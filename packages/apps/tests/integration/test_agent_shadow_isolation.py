"""Runtime and static proof that DecisionOpinion remains shadow-only."""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

import pytest
from ditto_agent._canonical import canonical_bytes
from ditto_agent.decision_opinion import DecisionOpinionGenerator
from ditto_agent.models.fake import ScriptedAgentModel, ScriptedOutcome
from ditto_agent.models.port import ModelResult, ModelUsage
from ditto_agent.storage.sqlite.errors import AgentIntegrityError
from ditto_agent.tools.registry import NO_APPROVAL_TOOL_NAMES
from ditto_application.processes.risk.agent_decision_briefing import (
    DecisionBriefingInput,
    DecisionBriefingProcess,
    DecisionOpinionGenerationRequest,
    DecisionOpinionWriteError,
)
from ditto_application.queries.daily_decision_v3 import (
    DailyDecisionV3Projection,
    FactorRiskSection,
    PortfolioConstructionSection,
    ProvenanceSection,
    ReconciliationSection,
    StressTestSection,
    TailRiskSection,
)
from ditto_application.queries.decision_briefing_contracts import (
    DecisionBriefingEvidenceReadModel,
)
from ditto_application.queries.evidence_contracts import (
    EvidenceArtifactReference,
    EvidencePayloadReadModel,
    EvidenceTemporalContext,
)
from ditto_execution.orders.ids import ClientOrderId
from ditto_execution.orders.model import Order
from ditto_kernel.identity import InstrumentId
from ditto_kernel.order import OrderSide, OrderType
from ditto_risk.continuous_gate import RiskDecision, RiskDecisionKind
from ditto_strategy.alpha.models import TargetPortfolio


@dataclass(frozen=True, slots=True)
class _CoreOutputs:
    daily_decision_v3: bytes
    recommended_weights: bytes
    risk_gate: bytes
    orders: bytes
    downstream_hash: str


def _core_outputs(
    *,
    readiness: str = "ready",
    weights: tuple[tuple[str, str], ...] = (("510300.SH", "0.60"),),
    risk_gate: str = "approved",
    orders: tuple[str, ...] = ("order-510300-buy-100",),
) -> _CoreOutputs:
    target = TargetPortfolio(
        trade_date="2026-08-15",
        strategy_id="strategy-1",
        run_id="run-1",
        positions={InstrumentId(1): float(weights[0][1])},
        cash_target=0.40,
    )
    projection = DailyDecisionV3Projection(
        portfolio_construction=PortfolioConstructionSection(
            status="optimal" if readiness == "ready" else "failed",
            mode="enforced",
            policy_digest="policy-1",
            solver="OSQP",
            solver_version="1.1.3",
            solver_status="optimal",
        ),
        tail_risk=TailRiskSection(
            historical_es99=0.04,
            historical_var99=0.03,
            parametric_var99=0.02,
            monte_carlo_var99=0.025,
            monte_carlo_seed=42,
        ),
        factor_risk=FactorRiskSection(
            availability="available",
            total_risk=0.02,
            marginal_contributions={"market": 0.02},
            percentage_contributions={"market": 1.0},
            euler_residual=0.0,
        ),
        stress_tests=StressTestSection(
            catalog_version="r4-v1",
            losses={"hypothetical:market-minus-10pct": 0.10},
        ),
        reconciliation=ReconciliationSection(
            status="reconciled",
            differences=(),
            alert_idempotency_key=None,
        ),
        provenance=ProvenanceSection(
            decision_time="2026-08-16T08:00:00Z",
            knowledge_cutoff="2026-08-16T07:00:00Z",
            publication_cutoff="2026-08-16T06:00:00Z",
            source_snapshot_ids=("snapshot-1",),
            generated_at="2026-08-16T08:01:00Z",
        ),
        blocking_reasons=() if readiness == "ready" else ("RISK_BLOCKED",),
    )
    order_records = tuple(
        Order(
            client_id=ClientOrderId(value=order_id),
            instrument_id=InstrumentId(1),
            order_type=OrderType.MARKET,
            direction=OrderSide.BUY,
            quantity=100,
            trade_date="2026-08-15",
        )
        for order_id in orders
    )
    v3 = canonical_bytes(projection)
    weight_bytes = canonical_bytes(
        {
            "trade_date": target.trade_date,
            "strategy_id": target.strategy_id,
            "run_id": target.run_id,
            "positions": tuple(
                (str(instrument_id), weight)
                for instrument_id, weight in sorted(target.positions.items())
            ),
            "cash_target": target.cash_target,
        }
    )
    risk_decision = RiskDecision(
        kind=(
            RiskDecisionKind.ALLOW
            if risk_gate == "approved"
            else RiskDecisionKind.REJECT
        ),
        reason_code=None if risk_gate == "approved" else "RISK_BLOCKED",
    )
    risk_bytes = canonical_bytes(risk_decision)
    order_bytes = canonical_bytes(order_records)
    downstream_digest = sha256()
    for payload in (v3, weight_bytes, risk_bytes, order_bytes):
        downstream_digest.update(len(payload).to_bytes(8, "big"))
        downstream_digest.update(payload)
    return _CoreOutputs(
        daily_decision_v3=v3,
        recommended_weights=weight_bytes,
        risk_gate=risk_bytes,
        orders=order_bytes,
        downstream_hash=downstream_digest.hexdigest(),
    )


def _unsafe_apply_malicious_opinion(
    baseline: _CoreOutputs,
    *,
    mutation: str,
) -> _CoreOutputs:
    """Reference anti-pattern used only to prove that the harness is sensitive."""
    if mutation == "daily_decision_v3":
        return replace(
            baseline,
            daily_decision_v3=canonical_bytes({"readiness": "blocked"}),
        )
    if mutation == "recommended_weights":
        return replace(
            baseline,
            recommended_weights=canonical_bytes((("510300.SH", "1.00"),)),
        )
    if mutation == "risk_gate":
        return replace(baseline, risk_gate=canonical_bytes("blocked"))
    if mutation == "orders":
        return replace(baseline, orders=canonical_bytes(("malicious-order",)))
    raise AssertionError(f"unknown mutation: {mutation}")


def _assert_core_outputs_equal(
    expected: _CoreOutputs,
    actual: _CoreOutputs,
) -> None:
    assert actual.daily_decision_v3 == expected.daily_decision_v3
    assert actual.recommended_weights == expected.recommended_weights
    assert actual.risk_gate == expected.risk_gate
    assert actual.orders == expected.orders
    assert actual.downstream_hash == expected.downstream_hash


@pytest.mark.parametrize(
    "mutation",
    ["daily_decision_v3", "recommended_weights", "risk_gate", "orders"],
)
def test_isolation_harness_observes_every_forbidden_downstream_mutation(
    mutation: str,
) -> None:
    baseline = _core_outputs()
    malicious = _unsafe_apply_malicious_opinion(baseline, mutation=mutation)

    with pytest.raises(AssertionError):
        _assert_core_outputs_equal(baseline, malicious)


def _context() -> EvidenceTemporalContext:
    return EvidenceTemporalContext(
        decision_time=datetime(2026, 8, 16, 8, tzinfo=UTC),
        knowledge_cutoff=datetime(2026, 8, 16, 7, tzinfo=UTC),
        publication_cutoff=datetime(2026, 8, 16, 6, tzinfo=UTC),
        source_snapshot_id="snapshot-1",
    )


def _evidence() -> DecisionBriefingEvidenceReadModel:
    payload = EvidencePayloadReadModel.seal(
        schema_version=1,
        value={
            "readiness": "ready",
            "blocking_reasons": (),
            "portfolio_construction": {"status": "optimal"},
            "provenance": {"source_snapshot_ids": ("snapshot-1",)},
        },
    )
    return DecisionBriefingEvidenceReadModel(
        strategy_id="strategy-1",
        strategy_version="3",
        trade_date="2026-08-15",
        account_id="account-1",
        sleeve_id="sleeve-1",
        readiness="ready",
        blocking_reasons=(),
        temporal_context=_context(),
        payload=payload,
        artifact_refs=(
            EvidenceArtifactReference(
                artifact_id="daily-decision-v3:strategy-1:2026-08-15",
                artifact_kind="daily_decision_v3",
                content_hash=payload.payload_hash,
            ),
        ),
        lineage=("decision:2026-08-15", "snapshot:snapshot-1"),
    )


class _EvidenceReader:
    def __init__(self, evidence: DecisionBriefingEvidenceReadModel) -> None:
        self._evidence = evidence

    def get_briefing_evidence(self, **_: object) -> DecisionBriefingEvidenceReadModel:
        return self._evidence


def _input() -> DecisionBriefingInput:
    return DecisionBriefingInput(
        strategy_id="strategy-1",
        strategy_version="3",
        trade_date="2026-08-15",
        account_id="account-1",
        sleeve_id="sleeve-1",
        context=_context(),
        generated_at=datetime(2026, 8, 16, 8, 1, tzinfo=UTC),
    )


def _model(evidence: DecisionBriefingEvidenceReadModel) -> ScriptedAgentModel:
    return ScriptedAgentModel(
        script=(
            ScriptedOutcome(
                result=ModelResult(
                    final_output={
                        "summary": "V3 remains authoritative and unchanged.",
                        "dissent": "Tail risk deserves review.",
                        "uncertainty": "This is a shadow interpretation.",
                        "evidence_refs": [evidence.artifact_refs[0].artifact_id],
                    },
                    tool_calls=(),
                    usage=ModelUsage(
                        requests=1,
                        input_tokens=100,
                        output_tokens=40,
                    ),
                    interruptions=(),
                    continuation=None,
                )
            ),
        )
    )


@pytest.mark.asyncio
async def test_shadow_on_off_keeps_all_core_outputs_byte_identical(
    tmp_path: Path,
) -> None:
    from ditto_apps.registry.agent.decision_briefing import (
        build_decision_opinion_shadow_store,
    )

    baseline = _core_outputs()
    shadow_disabled = _core_outputs()
    _assert_core_outputs_equal(baseline, shadow_disabled)

    bundle = build_decision_opinion_shadow_store(tmp_path)
    evidence = _evidence()
    model = _model(evidence)
    process = DecisionBriefingProcess(
        evidence_reader=_EvidenceReader(evidence),
        generator=DecisionOpinionGenerator(
            model=model,
            model_profile="balanced",
            provider_id="scripted",
            max_output_tokens=512,
        ),
        writer=bundle.writer,
    )

    outcome = await process.execute(_input())

    assert outcome.status == "persisted"
    assert outcome.opinion_id is not None
    record = bundle.reader.get_opinion(outcome.opinion_id)
    assert record is not None
    assert bundle.writer.append_opinion(record) is False
    events = bundle.reader.list_events(outcome.opinion_id)
    assert len(events) == 1
    assert events[0].event_type == "shadow_decision_opinion_persisted"
    _assert_core_outputs_equal(baseline, _core_outputs())
    assert model.requests[0].tools == ()

    connection = bundle.database.get_connection()
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            "UPDATE shadow_decision_opinions SET payload_json=? WHERE opinion_id=?",
            (b"{}", outcome.opinion_id),
        )
    connection.rollback()
    connection.execute("DROP TRIGGER shadow_decision_opinions_no_update")
    connection.execute(
        "UPDATE shadow_decision_opinions SET payload_json=? WHERE opinion_id=?",
        (b"{}", outcome.opinion_id),
    )
    connection.commit()
    with pytest.raises(AgentIntegrityError):
        bundle.reader.get_opinion(outcome.opinion_id)
    bundle.close()


def test_shadow_store_has_independent_database_and_event_namespace(
    tmp_path: Path,
) -> None:
    from ditto_apps.registry.agent.decision_briefing import (
        build_decision_opinion_shadow_store,
    )

    bundle = build_decision_opinion_shadow_store(tmp_path)

    assert bundle.database.path == (
        tmp_path / "agent-shadow" / "decision-opinion.sqlite"
    )
    assert bundle.database.catalog_names() == (
        "shadow_decision_events",
        "shadow_decision_events_no_delete",
        "shadow_decision_events_no_update",
        "shadow_decision_opinions",
        "shadow_decision_opinions_no_delete",
        "shadow_decision_opinions_no_update",
    )
    assert bundle.database.path != tmp_path / "agent" / "agent.sqlite"
    bundle.close()


def test_shadow_has_no_downstream_consumer_or_financial_tool_surface() -> None:
    repo_root = Path(__file__).resolve().parents[4]
    downstream_roots = (
        repo_root / "packages" / "portfolio" / "src",
        repo_root / "packages" / "risk" / "src",
        repo_root / "packages" / "execution" / "src",
        repo_root / "packages" / "apps" / "src" / "ditto_apps" / "jobs",
        repo_root
        / "packages"
        / "application"
        / "src"
        / "ditto_application"
        / "processes"
        / "portfolio",
        repo_root
        / "packages"
        / "application"
        / "src"
        / "ditto_application"
        / "processes"
        / "execution",
        repo_root
        / "packages"
        / "application"
        / "src"
        / "ditto_application"
        / "processes"
        / "risk",
    )
    needles = ("DecisionOpinion", "decision_opinion", "shadow_decision")
    offenders = tuple(
        path.relative_to(repo_root).as_posix()
        for root in downstream_roots
        for path in root.rglob("*.py")
        if path.name != "agent_decision_briefing.py"
        if any(needle in path.read_text(encoding="utf-8") for needle in needles)
    )

    assert offenders == ()
    assert all(
        forbidden not in tool_name
        for tool_name in NO_APPROVAL_TOOL_NAMES
        for forbidden in ("publish", "order", "broker", "trade")
    )


class _MaliciousOpinion:
    def __init__(self, payload: Mapping[str, object]) -> None:
        self._payload = payload

    def record_payload(self) -> Mapping[str, object]:
        return {
            **self._payload,
            "weights": {"510300.SH": 1.0},
            "risk_status": "approved",
            "orders": ("malicious-order",),
        }

    def verify_integrity(self) -> bool:
        return True


class _MaliciousGenerator:
    def __init__(self, payload: Mapping[str, object]) -> None:
        self._opinion = _MaliciousOpinion(payload)

    async def generate(
        self,
        _request: DecisionOpinionGenerationRequest,
    ) -> _MaliciousOpinion:
        return self._opinion


class _FailingWriter:
    def append_opinion(self, _record: object) -> bool:
        raise DecisionOpinionWriteError("shadow store unavailable")


@pytest.mark.asyncio
async def test_shadow_writer_failure_cannot_fail_or_mutate_core_outputs() -> None:
    evidence = _evidence()
    baseline = _core_outputs()

    outcome = await DecisionBriefingProcess(
        evidence_reader=_EvidenceReader(evidence),
        generator=DecisionOpinionGenerator(
            model=_model(evidence),
            model_profile="balanced",
            provider_id="scripted",
            max_output_tokens=512,
        ),
        writer=_FailingWriter(),
    ).execute(_input())

    assert outcome.status == "refused"
    assert outcome.reason_code == "decision_opinion_write_failed"
    _assert_core_outputs_equal(baseline, _core_outputs())


@pytest.mark.asyncio
async def test_malicious_opinion_cannot_write_or_mutate_downstream_outputs(
    tmp_path: Path,
) -> None:
    from ditto_apps.registry.agent.decision_briefing import (
        build_decision_opinion_shadow_store,
    )

    evidence = _evidence()
    opinion = await DecisionOpinionGenerator(
        model=_model(evidence),
        model_profile="balanced",
        provider_id="scripted",
        max_output_tokens=512,
    ).generate(
        DecisionOpinionGenerationRequest(
            evidence=evidence,
            generated_at=_input().generated_at,
        )
    )
    bundle = build_decision_opinion_shadow_store(tmp_path)
    baseline = _core_outputs()

    outcome = await DecisionBriefingProcess(
        evidence_reader=_EvidenceReader(evidence),
        generator=_MaliciousGenerator(opinion.record_payload()),
        writer=bundle.writer,
    ).execute(_input())

    assert outcome.status == "refused"
    assert outcome.reason_code == "decision_opinion_evidence_conflict"
    assert bundle.reader.count_opinions() == 0
    _assert_core_outputs_equal(baseline, _core_outputs())
    bundle.close()
