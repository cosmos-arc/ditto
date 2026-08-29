"""Tests for the Agent-owned shadow-only DecisionOpinion contract."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from datetime import UTC, datetime
from typing import Literal

import pytest
from ditto_agent.decision_opinion import (
    DecisionOpinion,
    DecisionOpinionGenerator,
    DecisionOpinionStatus,
)
from ditto_agent.models.fake import (
    ScriptedAgentModel,
    ScriptedFailure,
    ScriptedOutcome,
)
from ditto_agent.models.port import (
    ModelFailureKind,
    ModelResult,
    ModelUsage,
)
from ditto_application.processes.risk.agent_decision_briefing import (
    DecisionOpinionGenerationError,
    DecisionOpinionGenerationRequest,
)
from ditto_application.queries.decision_briefing_contracts import (
    DecisionBriefingEvidenceReadModel,
)
from ditto_application.queries.evidence_contracts import (
    EvidenceArtifactReference,
    EvidencePayloadReadModel,
    EvidenceTemporalContext,
)


def _evidence(
    *, readiness: Literal["ready", "blocked"] = "ready"
) -> DecisionBriefingEvidenceReadModel:
    context = EvidenceTemporalContext(
        decision_time=datetime(2026, 8, 16, 8, tzinfo=UTC),
        knowledge_cutoff=datetime(2026, 8, 16, 7, tzinfo=UTC),
        publication_cutoff=datetime(2026, 8, 16, 6, tzinfo=UTC),
        source_snapshot_id="snapshot-1",
    )
    payload = EvidencePayloadReadModel.seal(
        schema_version=1,
        value={
            "readiness": readiness,
            "blocking_reasons": (("RISK_BLOCKED",) if readiness == "blocked" else ()),
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
        readiness=readiness,
        blocking_reasons=("RISK_BLOCKED",) if readiness == "blocked" else (),
        temporal_context=context,
        payload=payload,
        artifact_refs=(
            EvidenceArtifactReference(
                artifact_id="daily-decision-v3:strategy-1:2026-08-15:account-1:sleeve-1",
                artifact_kind="daily_decision_v3",
                content_hash=payload.payload_hash,
            ),
        ),
        lineage=("decision:2026-08-15:account-1", "snapshot:snapshot-1"),
    )


def _request(
    *, readiness: Literal["ready", "blocked"] = "ready"
) -> DecisionOpinionGenerationRequest:
    return DecisionOpinionGenerationRequest(
        evidence=_evidence(readiness=readiness),
        generated_at=datetime(2026, 8, 16, 8, 1, tzinfo=UTC),
    )


def _result(output: Mapping[str, object]) -> ModelResult:
    return ModelResult(
        final_output=output,
        tool_calls=(),
        usage=ModelUsage(requests=1, input_tokens=100, output_tokens=40),
        interruptions=(),
        continuation=None,
    )


def _generator(model: ScriptedAgentModel) -> DecisionOpinionGenerator:
    return DecisionOpinionGenerator(
        model=model,
        model_profile="balanced",
        provider_id="scripted",
        max_output_tokens=512,
    )


@pytest.mark.asyncio
async def test_ready_v3_generates_content_addressed_read_only_opinion() -> None:
    evidence = _evidence()
    artifact_id = evidence.artifact_refs[0].artifact_id
    model = ScriptedAgentModel(
        script=(
            ScriptedOutcome(
                result=_result(
                    {
                        "summary": "Risk evidence is internally consistent.",
                        "dissent": "Tail loss remains material.",
                        "uncertainty": "Factor estimates may be partial.",
                        "evidence_refs": [artifact_id],
                    }
                )
            ),
        )
    )

    opinion = await _generator(model).generate(
        DecisionOpinionGenerationRequest(
            evidence=evidence,
            generated_at=datetime(2026, 8, 16, 8, 1, tzinfo=UTC),
        )
    )

    assert opinion.status is DecisionOpinionStatus.COMPLETED
    assert opinion.v3_evidence_hash == evidence.payload.payload_hash
    assert opinion.evidence_refs == (artifact_id,)
    assert opinion.verify_integrity()
    assert opinion.opinion_id == f"decision-opinion-{opinion.opinion_hash}"
    assert opinion.shadow_outcome_id == f"decision-shadow-{opinion.opinion_hash}"
    request = model.requests[0]
    assert request.tools == ()
    assert request.max_turns == 1
    assert not {
        "weights",
        "risk_status",
        "actions",
        "orders",
    }.intersection(DecisionOpinion.__dataclass_fields__)


@pytest.mark.asyncio
async def test_same_v3_and_output_have_byte_stable_shadow_identity() -> None:
    artifact_id = _evidence().artifact_refs[0].artifact_id
    output = {
        "summary": "Stable explanation.",
        "dissent": None,
        "uncertainty": "Shadow-only.",
        "evidence_refs": [artifact_id],
    }
    first = await _generator(
        ScriptedAgentModel(script=(ScriptedOutcome(result=_result(output)),))
    ).generate(_request())
    second = await _generator(
        ScriptedAgentModel(script=(ScriptedOutcome(result=_result(output)),))
    ).generate(_request())

    assert first == second
    assert first.opinion_hash == second.opinion_hash
    assert not replace(first, summary="Tampered explanation.").verify_integrity()


@pytest.mark.asyncio
async def test_blocked_v3_is_explained_deterministically_without_model_call() -> None:
    model = ScriptedAgentModel()

    opinion = await _generator(model).generate(_request(readiness="blocked"))

    assert opinion.status is DecisionOpinionStatus.BLOCKED
    assert opinion.blocking_reasons == ("RISK_BLOCKED",)
    assert opinion.reason_code == "daily_decision_v3_blocked"
    assert "RISK_BLOCKED" in opinion.summary
    assert not model.requests


@pytest.mark.asyncio
async def test_model_failure_is_typed_and_does_not_fabricate_an_opinion() -> None:
    model = ScriptedAgentModel(
        script=(
            ScriptedFailure(
                kind=ModelFailureKind.PROVIDER,
                message="provider unavailable",
            ),
        )
    )

    with pytest.raises(DecisionOpinionGenerationError) as exc_info:
        await _generator(model).generate(_request())

    assert exc_info.value.details["reason_code"] == "model_provider_failed"


@pytest.mark.asyncio
@pytest.mark.parametrize("mutation", ["artifact_hash", "empty_blocking_reasons"])
async def test_tampered_v3_read_model_fails_before_model_call(mutation: str) -> None:
    evidence = _evidence(readiness="blocked")
    if mutation == "artifact_hash":
        evidence = replace(
            evidence,
            artifact_refs=(replace(evidence.artifact_refs[0], content_hash="f" * 64),),
        )
    else:
        evidence = replace(evidence, blocking_reasons=())
    model = ScriptedAgentModel()

    with pytest.raises(DecisionOpinionGenerationError) as exc_info:
        await _generator(model).generate(
            DecisionOpinionGenerationRequest(
                evidence=evidence,
                generated_at=datetime(2026, 8, 16, 8, 1, tzinfo=UTC),
            )
        )

    assert exc_info.value.details["reason_code"] == "decision_evidence_invalid"
    assert not model.requests


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "output",
    [
        {
            "summary": "Unbound evidence.",
            "dissent": None,
            "uncertainty": "Unknown.",
            "evidence_refs": ["other-artifact"],
        },
        {
            "summary": "Attempted mutation.",
            "dissent": None,
            "uncertainty": "Unknown.",
            "evidence_refs": [
                "daily-decision-v3:strategy-1:2026-08-15:account-1:sleeve-1"
            ],
            "orders": [{"instrument_id": "510300", "quantity": 1}],
        },
    ],
)
async def test_conflicting_evidence_or_mutation_fields_fail_closed(
    output: Mapping[str, object],
) -> None:
    model = ScriptedAgentModel(script=(ScriptedOutcome(result=_result(output)),))

    with pytest.raises(DecisionOpinionGenerationError) as exc_info:
        await _generator(model).generate(_request())

    assert exc_info.value.details["reason_code"] == "model_output_invalid"
