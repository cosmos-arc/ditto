"""Tests for the post-V3 DecisionOpinion shadow process."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Literal

import pytest
from ditto_application.exceptions import AppQueryError
from ditto_application.processes.risk.agent_decision_briefing import (
    DecisionBriefingInput,
    DecisionBriefingProcess,
    DecisionOpinionGenerationError,
    DecisionOpinionRecord,
)
from ditto_application.queries.decision_briefing_contracts import (
    DecisionBriefingEvidenceReadModel,
)
from ditto_application.queries.evidence_contracts import (
    EvidenceArtifactReference,
    EvidencePayloadReadModel,
    EvidenceTemporalContext,
)


def _context() -> EvidenceTemporalContext:
    return EvidenceTemporalContext(
        decision_time=datetime(2026, 8, 16, 8, tzinfo=UTC),
        knowledge_cutoff=datetime(2026, 8, 16, 7, tzinfo=UTC),
        publication_cutoff=datetime(2026, 8, 16, 6, tzinfo=UTC),
        source_snapshot_id="snapshot-1",
    )


def _evidence(
    *, readiness: Literal["ready", "blocked"] = "ready"
) -> DecisionBriefingEvidenceReadModel:
    payload = EvidencePayloadReadModel.seal(
        schema_version=1,
        value={
            "readiness": readiness,
            "blocking_reasons": (("RISK_BLOCKED",) if readiness == "blocked" else ()),
            "provenance": {
                "decision_time": "2026-08-16T08:00:00Z",
                "knowledge_cutoff": "2026-08-16T07:00:00Z",
                "publication_cutoff": "2026-08-16T06:00:00Z",
                "source_snapshot_ids": ("snapshot-1",),
            },
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
        temporal_context=_context(),
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


@dataclass(frozen=True)
class _Opinion:
    schema_version: int
    opinion_id: str
    shadow_outcome_id: str
    status: str
    v3_artifact_id: str
    v3_evidence_hash: str
    v3_readiness: str
    summary: str
    dissent: str | None
    uncertainty: str
    evidence_refs: tuple[str, ...]
    blocking_reasons: tuple[str, ...]
    reason_code: str | None
    model_profile: str
    prompt_hash: str
    provider_id: str
    generated_at: datetime
    opinion_hash: str

    def record_payload(self) -> dict[str, object]:
        """Project the fake through the same strict record boundary."""
        return {
            field_name: getattr(self, field_name)
            for field_name in DecisionOpinionRecord.__dataclass_fields__
        }

    def verify_integrity(self) -> bool:
        """Act as an already verified trusted generator result."""
        return True


def _opinion(evidence: DecisionBriefingEvidenceReadModel) -> _Opinion:
    artifact_id = evidence.artifact_refs[0].artifact_id
    return _Opinion(
        schema_version=1,
        opinion_id=f"decision-opinion-{'a' * 64}",
        shadow_outcome_id=f"decision-shadow-{'a' * 64}",
        status="blocked" if evidence.readiness == "blocked" else "completed",
        v3_artifact_id=artifact_id,
        v3_evidence_hash=evidence.payload.payload_hash,
        v3_readiness=evidence.readiness,
        summary="V3 evidence remains unchanged and is explained read-only.",
        dissent=None,
        uncertainty="The opinion is advisory and shadow-only.",
        evidence_refs=(artifact_id,),
        blocking_reasons=evidence.blocking_reasons,
        reason_code=(
            "daily_decision_v3_blocked" if evidence.readiness == "blocked" else None
        ),
        model_profile="balanced",
        prompt_hash="b" * 64,
        provider_id="scripted",
        generated_at=datetime(2026, 8, 16, 8, 1, tzinfo=UTC),
        opinion_hash="a" * 64,
    )


class _Reader:
    def __init__(
        self,
        evidence: DecisionBriefingEvidenceReadModel | None = None,
        error: AppQueryError | None = None,
    ) -> None:
        self.evidence = evidence
        self.error = error
        self.calls = 0

    def get_briefing_evidence(self, **_: object) -> DecisionBriefingEvidenceReadModel:
        self.calls += 1
        if self.error is not None:
            raise self.error
        assert self.evidence is not None
        return self.evidence


class _Generator:
    def __init__(
        self,
        opinion: _Opinion | None = None,
        error: DecisionOpinionGenerationError | None = None,
    ) -> None:
        self.opinion = opinion
        self.error = error
        self.requests: list[object] = []

    async def generate(self, request: object) -> _Opinion:
        self.requests.append(request)
        if self.error is not None:
            raise self.error
        assert self.opinion is not None
        return self.opinion


class _Writer:
    def __init__(self) -> None:
        self.records: list[DecisionOpinionRecord] = []

    def append_opinion(self, record: DecisionOpinionRecord) -> bool:
        self.records.append(record)
        return True


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


@pytest.mark.asyncio
@pytest.mark.parametrize("readiness", ["ready", "blocked"])
async def test_post_v3_process_persists_only_an_independent_shadow_record(
    readiness: Literal["ready", "blocked"],
) -> None:
    evidence = _evidence(readiness=readiness)
    reader = _Reader(evidence)
    generator = _Generator(_opinion(evidence))
    writer = _Writer()
    process = DecisionBriefingProcess(
        evidence_reader=reader,
        generator=generator,
        writer=writer,
    )

    outcome = await process.execute(_input())

    assert outcome.status == "persisted"
    assert outcome.reason_code is None
    assert outcome.opinion_id == writer.records[0].opinion_id
    assert writer.records[0].v3_evidence_hash == evidence.payload.payload_hash
    assert writer.records[0].shadow_outcome_id.startswith("decision-shadow-")
    assert not {
        "weights",
        "risk_status",
        "actions",
        "orders",
    }.intersection(DecisionOpinionRecord.__dataclass_fields__)
    assert reader.calls == 1
    assert len(generator.requests) == 1


@pytest.mark.asyncio
async def test_missing_or_invalid_v3_evidence_refuses_before_model_or_write() -> None:
    reader = _Reader(
        error=AppQueryError(
            "V3 missing",
            details={"code": "EVIDENCE_PROVENANCE_INCOMPLETE"},
        )
    )
    generator = _Generator()
    writer = _Writer()

    outcome = await DecisionBriefingProcess(
        evidence_reader=reader,
        generator=generator,
        writer=writer,
    ).execute(_input())

    assert outcome.status == "refused"
    assert outcome.reason_code == "EVIDENCE_PROVENANCE_INCOMPLETE"
    assert not generator.requests
    assert not writer.records


@pytest.mark.asyncio
async def test_model_failure_refuses_without_fabricating_or_persisting_opinion() -> (
    None
):
    evidence = _evidence()
    generator = _Generator(
        error=DecisionOpinionGenerationError(
            "provider unavailable",
            reason_code="model_provider_failed",
        )
    )
    writer = _Writer()

    outcome = await DecisionBriefingProcess(
        evidence_reader=_Reader(evidence),
        generator=generator,
        writer=writer,
    ).execute(_input())

    assert outcome.status == "refused"
    assert outcome.reason_code == "model_provider_failed"
    assert not writer.records


@pytest.mark.asyncio
async def test_evidence_conflict_is_rejected_before_shadow_persistence() -> None:
    evidence = _evidence()
    conflicted = replace(_opinion(evidence), v3_evidence_hash="f" * 64)
    writer = _Writer()

    outcome = await DecisionBriefingProcess(
        evidence_reader=_Reader(evidence),
        generator=_Generator(conflicted),
        writer=writer,
    ).execute(_input())

    assert outcome.status == "refused"
    assert outcome.reason_code == "decision_opinion_evidence_conflict"
    assert not writer.records
