"""Exact-identity DecisionOpinion read projection contracts."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

import pytest
from ditto_application.processes.risk.agent_decision_briefing import (
    DecisionOpinionRecord,
)
from ditto_application.queries.decision_briefing_contracts import (
    DecisionBriefingEvidenceReadModel,
)
from ditto_application.queries.decision_opinion import (
    DecisionOpinionIdentity,
    DecisionOpinionQueryService,
)
from ditto_application.queries.evidence_contracts import (
    EvidenceArtifactReference,
    EvidencePayloadReadModel,
    EvidenceTemporalContext,
)

ARTIFACT_ID = "daily-decision-v3:strategy-1:2026-08-15:account-1:sleeve-1"
GENERATED_AT = datetime(2026, 8, 16, 8, 1, tzinfo=UTC)


def _context() -> EvidenceTemporalContext:
    return EvidenceTemporalContext(
        decision_time=datetime(2026, 8, 16, 8, 0, tzinfo=UTC),
        knowledge_cutoff=datetime(2026, 8, 16, 7, 0, tzinfo=UTC),
        publication_cutoff=datetime(2026, 8, 16, 6, 0, tzinfo=UTC),
        source_snapshot_id="snapshot-1",
    )


def _evidence() -> DecisionBriefingEvidenceReadModel:
    payload = EvidencePayloadReadModel.seal(
        schema_version=1,
        value={
            "readiness": "ready",
            "blocking_reasons": (),
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
                artifact_id=ARTIFACT_ID,
                artifact_kind="daily_decision_v3",
                content_hash=payload.payload_hash,
            ),
        ),
        lineage=("snapshot:snapshot-1",),
    )


def _record() -> DecisionOpinionRecord:
    evidence = _evidence()
    return DecisionOpinionRecord(
        schema_version=1,
        opinion_id="decision-opinion-" + "a" * 64,
        shadow_outcome_id="decision-shadow-" + "a" * 64,
        status="completed",
        v3_artifact_id=ARTIFACT_ID,
        v3_evidence_hash=evidence.payload.payload_hash,
        v3_readiness="ready",
        summary="Risk evidence is internally consistent.",
        dissent="Tail loss remains material.",
        uncertainty="Factor estimates may be partial.",
        evidence_refs=(ARTIFACT_ID,),
        blocking_reasons=(),
        reason_code=None,
        model_profile="balanced",
        prompt_hash="b" * 64,
        provider_id="scripted",
        generated_at=GENERATED_AT,
        opinion_hash="a" * 64,
    )


class _EvidenceReader:
    def __init__(self, evidence: DecisionBriefingEvidenceReadModel) -> None:
        self.evidence = evidence

    def get_briefing_evidence(self, **_: object) -> DecisionBriefingEvidenceReadModel:
        return self.evidence


class _OpinionReader:
    def __init__(self, record: DecisionOpinionRecord | None) -> None:
        self.record = record
        self.artifact_ids: list[str] = []

    def get_latest_by_v3_artifact_id(
        self, v3_artifact_id: str
    ) -> DecisionOpinionRecord | None:
        self.artifact_ids.append(v3_artifact_id)
        return self.record


def _identity(
    *, context: EvidenceTemporalContext | None = None
) -> DecisionOpinionIdentity:
    return DecisionOpinionIdentity(
        strategy_id="strategy-1",
        strategy_version="3",
        trade_date="2026-08-15",
        account_id="account-1",
        sleeve_id="sleeve-1",
        v3_artifact_id=ARTIFACT_ID,
        context=context or _context(),
    )


def test_exact_v3_identity_returns_readable_shadow_projection() -> None:
    opinion_reader = _OpinionReader(_record())
    view = DecisionOpinionQueryService(
        evidence_reader=_EvidenceReader(_evidence()),
        opinion_reader=opinion_reader,
    ).get_opinion(_identity())

    assert view.status == "completed"
    assert view.identity == _identity()
    assert view.generated_at == GENERATED_AT
    assert view.model_profile == "balanced"
    assert view.summary == "Risk evidence is internally consistent."
    assert view.disagreements == ("Tail loss remains material.",)
    assert view.uncertainties == ("Factor estimates may be partial.",)
    assert view.evidence_refs == (ARTIFACT_ID,)
    assert view.provenance_match is True
    assert view.shadow_outcome_identity == "decision-shadow-" + "a" * 64
    assert view.unavailable_reason is None
    assert opinion_reader.artifact_ids == [ARTIFACT_ID]


@pytest.mark.parametrize(
    "context",
    [
        replace(
            _context(),
            publication_cutoff=datetime(2026, 8, 16, 6, 30, tzinfo=UTC),
        ),
        replace(_context(), source_snapshot_id="FUTURE_SNAPSHOT_SENTINEL"),
    ],
)
def test_future_cutoff_or_snapshot_fails_closed_for_opinion_only(
    context: EvidenceTemporalContext,
) -> None:
    evidence = _evidence()
    view = DecisionOpinionQueryService(
        evidence_reader=_EvidenceReader(evidence),
        opinion_reader=_OpinionReader(_record()),
    ).get_opinion(_identity(context=context))

    assert view.status == "unavailable"
    assert view.provenance_match is False
    assert view.summary is None
    assert view.unavailable_reason == "decision_opinion_provenance_mismatch"
    assert evidence.readiness == "ready"
    assert evidence.payload.value["readiness"] == "ready"


def test_missing_or_hash_mismatched_opinion_is_explicitly_unavailable() -> None:
    service = DecisionOpinionQueryService(
        evidence_reader=_EvidenceReader(_evidence()),
        opinion_reader=_OpinionReader(replace(_record(), v3_evidence_hash="f" * 64)),
    )

    view = service.get_opinion(_identity())

    assert view.status == "unavailable"
    assert view.provenance_match is False
    assert view.unavailable_reason == "decision_opinion_provenance_mismatch"
