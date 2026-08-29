"""Pure PIT-safe research feedback and long-term memory contracts."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Self, cast

from ditto_analysis.errors import ExperimentSpecError
from ditto_analysis.experiments._validation import require_utc_datetime
from ditto_analysis.experiments.models import (
    CandidateId,
    ContentHash,
    ExperimentId,
    SnapshotId,
)

__all__ = [
    "KnowledgeItem",
    "KnowledgeScope",
    "KnowledgeSource",
    "KnowledgeStatus",
    "KnowledgeStatusEvent",
    "ResearchFeedback",
]


def _memory_error(
    message: str,
    reason_code: str,
    **details: object,
) -> ExperimentSpecError:
    return ExperimentSpecError(
        message,
        details={"reason_code": reason_code, **details},
    )


def _non_empty(value: object, field: str) -> str:
    if type(value) is not str or not value.strip() or value != value.strip():
        raise _memory_error(
            f"{field} must be a non-empty unpadded string",
            "invalid_research_memory_text",
            field=field,
        )
    return value


def _freeze_evidence(value: object) -> tuple[ContentHash, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise _memory_error(
            "evidence_refs must be an ordered sequence",
            "invalid_research_memory_evidence",
        )
    raw = tuple(cast("Sequence[object]", value))
    if not raw or any(type(item) is not ContentHash for item in raw):
        raise _memory_error(
            "evidence_refs must contain ContentHash values",
            "invalid_research_memory_evidence",
        )
    typed = cast("tuple[ContentHash, ...]", raw)
    if len(set(typed)) != len(typed):
        raise _memory_error(
            "evidence_refs cannot contain duplicates",
            "invalid_research_memory_evidence",
        )
    return tuple(sorted(typed, key=str))


class KnowledgeScope(StrEnum):
    """Explicit applicability scope of one research knowledge item."""

    CAMPAIGN_LOCAL = "campaign-local"
    STRATEGY_FAMILY = "strategy-family"
    GLOBAL = "global"


class KnowledgeSource(StrEnum):
    """Typed provenance, including values that contracts must reject."""

    HOST_VALIDATION = "host_validation"
    INDEPENDENT_REPLICATION = "independent_replication"
    HUMAN_REVIEW = "human_review"
    MODEL_SELF_EVALUATION = "model_self_evaluation"
    UNVERIFIED_EXPLANATION = "unverified_explanation"
    HOLDOUT_RESULT = "holdout_result"


class KnowledgeStatus(StrEnum):
    """Append-only lifecycle states for research knowledge."""

    ACTIVE = "active"
    INVALIDATED = "invalidated"
    CONTRADICTED = "contradicted"
    REVOKED = "revoked"


_PROHIBITED_SOURCES = frozenset(
    {
        KnowledgeSource.MODEL_SELF_EVALUATION,
        KnowledgeSource.UNVERIFIED_EXPLANATION,
        KnowledgeSource.HOLDOUT_RESULT,
    }
)

_STATUS_RANK = {
    KnowledgeStatus.ACTIVE: 0,
    KnowledgeStatus.INVALIDATED: 1,
    KnowledgeStatus.CONTRADICTED: 2,
    KnowledgeStatus.REVOKED: 3,
}


def _validate_source(value: object, *, feedback: bool) -> KnowledgeSource:
    reason = (
        "prohibited_research_feedback_source"
        if feedback
        else "prohibited_research_memory_source"
    )
    if type(value) is not KnowledgeSource:
        raise _memory_error(
            "source must be KnowledgeSource",
            "invalid_research_memory_source",
        )
    source = value
    if source in _PROHIBITED_SOURCES:
        raise _memory_error(
            "model self-evaluation, unverified explanation, and holdout are prohibited",
            reason,
            source=source.value,
        )
    return source


def _require_visible[VisibleValue](
    value: VisibleValue,
    *,
    outcome_known_at: datetime,
    knowledge_cutoff: datetime,
) -> VisibleValue:
    cutoff = require_utc_datetime(knowledge_cutoff, "knowledge_cutoff")
    if outcome_known_at > cutoff:
        raise _memory_error(
            "research memory outcome is not yet visible at the cutoff",
            "research_memory_not_yet_known",
        )
    return value


@dataclass(frozen=True, slots=True)
class KnowledgeItem:
    """PIT-visible long-term research knowledge with explicit promotion proof."""

    knowledge_id: str
    campaign_id: ExperimentId
    claim: str
    scope: KnowledgeScope
    scope_ref: str | None
    evidence_refs: Sequence[ContentHash]
    outcome_known_at: datetime
    snapshot_id: SnapshotId
    source: KnowledgeSource
    source_hash: ContentHash
    status: KnowledgeStatus
    promotion_receipt_hash: ContentHash | None
    independent_evidence_hash: ContentHash | None

    def __post_init__(self) -> None:
        """Reject future-unsafe, untrusted, or unapproved long-term knowledge."""
        _non_empty(self.knowledge_id, "knowledge_id")
        _non_empty(self.claim, "claim")
        for value, expected, field in (
            (self.campaign_id, ExperimentId, "campaign_id"),
            (self.scope, KnowledgeScope, "scope"),
            (self.snapshot_id, SnapshotId, "snapshot_id"),
            (self.source_hash, ContentHash, "source_hash"),
            (self.status, KnowledgeStatus, "status"),
        ):
            if type(value) is not expected:
                raise _memory_error(
                    f"{field} must be {expected.__name__}",
                    "invalid_research_memory_item",
                    field=field,
                )
        require_utc_datetime(self.outcome_known_at, "outcome_known_at")
        _validate_source(self.source, feedback=False)
        object.__setattr__(self, "evidence_refs", _freeze_evidence(self.evidence_refs))
        self._validate_scope()

    def _validate_scope(self) -> None:
        if self.scope is KnowledgeScope.STRATEGY_FAMILY:
            if (
                type(self.scope_ref) is not str
                or not self.scope_ref.strip()
                or self.scope_ref != self.scope_ref.strip()
            ):
                raise _memory_error(
                    "strategy-family memory requires an exact scope_ref",
                    "invalid_research_memory_scope",
                )
        elif self.scope_ref is not None:
            raise _memory_error(
                "scope_ref is only allowed for strategy-family knowledge",
                "invalid_research_memory_scope",
            )
        promoted = self.scope is not KnowledgeScope.CAMPAIGN_LOCAL
        proof = (self.promotion_receipt_hash, self.independent_evidence_hash)
        if promoted and any(type(item) is not ContentHash for item in proof):
            raise _memory_error(
                "non-local memory requires approval and independent evidence",
                "research_memory_promotion_unproven",
            )
        if not promoted and any(item is not None for item in proof):
            raise _memory_error(
                "campaign-local memory cannot carry promotion proof",
                "invalid_research_memory_scope",
            )

    def require_visible_at(self, knowledge_cutoff: datetime) -> Self:
        """Return this item only when it was knowable by the UTC cutoff."""
        return _require_visible(
            self,
            outcome_known_at=self.outcome_known_at,
            knowledge_cutoff=knowledge_cutoff,
        )


@dataclass(frozen=True, slots=True)
class ResearchFeedback:
    """Structured non-holdout feedback eligible for a later search generation."""

    campaign_id: ExperimentId
    candidate_id: CandidateId
    evaluation_result_hash: ContentHash
    summary: str
    evidence_refs: Sequence[ContentHash]
    outcome_known_at: datetime
    snapshot_id: SnapshotId
    source: KnowledgeSource

    def __post_init__(self) -> None:
        """Require host-grounded feedback and reject holdout/model input."""
        _non_empty(self.summary, "summary")
        for value, expected, field in (
            (self.campaign_id, ExperimentId, "campaign_id"),
            (self.candidate_id, CandidateId, "candidate_id"),
            (
                self.evaluation_result_hash,
                ContentHash,
                "evaluation_result_hash",
            ),
            (self.snapshot_id, SnapshotId, "snapshot_id"),
        ):
            if type(value) is not expected:
                raise _memory_error(
                    f"{field} must be {expected.__name__}",
                    "invalid_research_feedback",
                    field=field,
                )
        require_utc_datetime(self.outcome_known_at, "outcome_known_at")
        _validate_source(self.source, feedback=True)
        object.__setattr__(self, "evidence_refs", _freeze_evidence(self.evidence_refs))

    def require_visible_at(self, knowledge_cutoff: datetime) -> Self:
        """Return feedback only when its outcome was knowable by the cutoff."""
        return _require_visible(
            self,
            outcome_known_at=self.outcome_known_at,
            knowledge_cutoff=knowledge_cutoff,
        )


@dataclass(frozen=True, slots=True)
class KnowledgeStatusEvent:
    """One append-only monotonic status transition for a knowledge item."""

    event_id: str
    knowledge_id: str
    previous_status: KnowledgeStatus
    status: KnowledgeStatus
    outcome_known_at: datetime
    evidence_hash: ContentHash

    def __post_init__(self) -> None:
        """Allow knowledge to move monotonically away from active."""
        _non_empty(self.event_id, "event_id")
        _non_empty(self.knowledge_id, "knowledge_id")
        for value, expected, field in (
            (self.previous_status, KnowledgeStatus, "previous_status"),
            (self.status, KnowledgeStatus, "status"),
            (self.evidence_hash, ContentHash, "evidence_hash"),
        ):
            if type(value) is not expected:
                raise _memory_error(
                    f"{field} must be {expected.__name__}",
                    "invalid_knowledge_status_event",
                    field=field,
                )
        require_utc_datetime(self.outcome_known_at, "outcome_known_at")
        if _STATUS_RANK[self.status] <= _STATUS_RANK[self.previous_status]:
            raise _memory_error(
                "knowledge status transitions must move monotonically away from active",
                "invalid_knowledge_status_transition",
            )
