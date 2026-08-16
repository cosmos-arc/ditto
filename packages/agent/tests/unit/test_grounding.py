from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

from ditto_agent.contracts.evidence import EvidenceEnvelope
from ditto_agent.contracts.temporal import (
    EgressClass,
    TemporalContextInput,
    TemporalToolContext,
)
from ditto_agent.grounding import (
    GroundingBuilder,
    GroundingDraft,
    ToolExecutionFailure,
)


def _context(*, snapshot_id: str = "snapshot-20260812") -> TemporalToolContext:
    return TemporalToolContext.from_host(
        TemporalContextInput(
            decision_time=datetime(2026, 8, 12, 7, 0, tzinfo=UTC),
            knowledge_cutoff=datetime(2026, 8, 12, 6, 55, tzinfo=UTC),
            publication_cutoff=datetime(2026, 8, 12, 6, 50, tzinfo=UTC),
            source_snapshot_id=snapshot_id,
            execution_eligible_at="not_applicable",
            allowed_universe=("510300.SH",),
            license_class="internal_research",
            egress_class=EgressClass.LOCAL_ONLY,
        )
    )


def _evidence(
    evidence_id: str,
    *,
    context: TemporalToolContext | None = None,
) -> EvidenceEnvelope:
    return EvidenceEnvelope.seal(
        evidence_id=evidence_id,
        tool_name="research_experiment_evidence",
        result={"status": "completed", "payload_hash": "a" * 64},
        artifact_refs=("experiment:001:sha256:" + "a" * 64,),
        temporal_context=context or _context(),
        lineage=("experiment:001",),
    )


def test_grounding_builder_binds_every_claim_to_verified_evidence() -> None:
    evidence = _evidence("evidence-001")
    answer = GroundingBuilder(expected_context=_context()).build(
        drafts=(
            GroundingDraft(
                claim="The governed experiment completed.",
                evidence_refs=(evidence.evidence_id,),
            ),
        ),
        evidence=(evidence,),
        uncertainty="The result is limited to the registered snapshot.",
    )

    assert answer.refusal_reason is None
    assert answer.claims[0].evidence_refs == ("evidence-001",)
    assert answer.missing_evidence == ()


def test_missing_evidence_or_uncited_claim_forces_structured_refusal() -> None:
    evidence = _evidence("evidence-001")
    builder = GroundingBuilder(expected_context=_context())

    missing = builder.build(
        drafts=(
            GroundingDraft(
                claim="The metric improved.",
                evidence_refs=("evidence-404",),
            ),
        ),
        evidence=(evidence,),
    )
    uncited = builder.build(
        drafts=(GroundingDraft(claim="The metric improved.", evidence_refs=()),),
        evidence=(evidence,),
    )

    assert missing.claims == ()
    assert missing.refusal_reason == "missing_evidence"
    assert missing.missing_evidence == ("evidence-404",)
    assert uncited.claims == ()
    assert uncited.refusal_reason == "missing_evidence"
    assert uncited.missing_evidence == ("claim:1",)


def test_tool_error_cannot_be_rewritten_into_a_grounded_fact() -> None:
    evidence = _evidence("evidence-001")
    answer = GroundingBuilder(expected_context=_context()).build(
        drafts=(
            GroundingDraft(
                claim="The missing strategy passed validation.",
                evidence_refs=(evidence.evidence_id,),
            ),
        ),
        evidence=(evidence,),
        tool_failures=(
            ToolExecutionFailure(
                call_id="call-001",
                tool_name="research_strategy_evidence",
                error_code="EVIDENCE_NOT_FOUND",
            ),
        ),
    )

    assert answer.claims == ()
    assert answer.refusal_reason == "tool_execution_failed"
    assert answer.missing_evidence == ("tool:research_strategy_evidence:call-001",)


def test_tampered_conflicting_or_wrong_snapshot_evidence_forces_refusal() -> None:
    context = _context()
    verified = _evidence("evidence-001", context=context)
    tampered = replace(verified, result={"status": "failed"})
    wrong_snapshot = _evidence(
        "evidence-002",
        context=_context(snapshot_id="future-snapshot"),
    )
    conflicting = replace(verified, integrity_hash="b" * 64)
    builder = GroundingBuilder(expected_context=context)

    tampered_answer = builder.build(
        drafts=(GroundingDraft("Claim", (tampered.evidence_id,)),),
        evidence=(tampered,),
    )
    context_answer = builder.build(
        drafts=(GroundingDraft("Claim", (wrong_snapshot.evidence_id,)),),
        evidence=(wrong_snapshot,),
    )
    conflict_answer = builder.build(
        drafts=(GroundingDraft("Claim", (verified.evidence_id,)),),
        evidence=(verified, conflicting),
    )

    assert tampered_answer.refusal_reason == "evidence_integrity_failed"
    assert context_answer.refusal_reason == "evidence_context_conflict"
    assert conflict_answer.refusal_reason == "conflicting_evidence_identity"
