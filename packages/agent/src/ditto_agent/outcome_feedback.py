"""PIT-bound, immutable outcome feedback for shadow DecisionOpinion records."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from types import MappingProxyType
from typing import cast

from ditto_application.processes.risk.agent_decision_briefing import (
    DecisionOpinionRecord,
)
from ditto_application.queries.evidence_contracts import EvidenceTemporalContext

from ditto_agent._canonical import canonical_sha256
from ditto_agent.contracts._validation import (
    enum_value,
    normalized_text,
    normalized_unique_tuple,
    sha256_hex,
    utc_datetime,
)

_BASIS_POINTS = 10_000


class DecisionOutcomeFeedbackError(ValueError):
    """A shadow outcome could not be linked without violating PIT controls."""

    def __init__(self, message: str, *, reason_code: str) -> None:
        super().__init__(message)
        self.reason_code = reason_code
        self.details = MappingProxyType({"reason_code": reason_code})


class DecisionOpinionAdoption(StrEnum):
    """Operator adoption observation, never an automated promotion decision."""

    NOT_REVIEWED = "not_reviewed"
    REVIEWED = "reviewed"
    ADOPTED = "adopted"
    REJECTED = "rejected"


@dataclass(frozen=True, slots=True)
class DecisionOutcomeObservationInput:
    """Host-owned fields sealed into one outcome observation."""

    opinion_id: str
    shadow_outcome_id: str
    outcome_kind: str
    outcome_period_start: datetime
    outcome_period_end: datetime
    outcome_known_at: datetime
    published_at: datetime
    source_snapshot_id: str
    evidence_refs: tuple[str, ...]
    adoption: DecisionOpinionAdoption
    accuracy_basis_points: int
    calibration_basis_points: int
    is_holdout: bool


@dataclass(frozen=True, slots=True)
class DecisionOutcomeObservation:
    """Host-scored outcome metadata with no raw return or prompt content."""

    schema_version: int
    observation_id: str
    opinion_id: str
    shadow_outcome_id: str
    outcome_kind: str
    outcome_period_start: datetime
    outcome_period_end: datetime
    outcome_known_at: datetime
    published_at: datetime
    source_snapshot_id: str
    evidence_refs: tuple[str, ...]
    adoption: DecisionOpinionAdoption
    accuracy_basis_points: int
    calibration_basis_points: int
    is_holdout: bool
    observation_hash: str

    def __post_init__(self) -> None:
        """Normalize every field and verify the content identity."""
        if self.schema_version != 1:
            raise ValueError("DecisionOutcomeObservation schema_version must be 1")
        for field_name in (
            "observation_id",
            "opinion_id",
            "shadow_outcome_id",
            "outcome_kind",
            "source_snapshot_id",
        ):
            object.__setattr__(
                self,
                field_name,
                normalized_text(getattr(self, field_name), field=field_name),
            )
        for field_name in (
            "outcome_period_start",
            "outcome_period_end",
            "outcome_known_at",
            "published_at",
        ):
            object.__setattr__(
                self,
                field_name,
                utc_datetime(getattr(self, field_name), field=field_name),
            )
        object.__setattr__(
            self,
            "evidence_refs",
            normalized_unique_tuple(self.evidence_refs, field="evidence_refs"),
        )
        enum_value(self.adoption, DecisionOpinionAdoption, field="adoption")
        object.__setattr__(
            self,
            "observation_hash",
            sha256_hex(self.observation_hash, field="observation_hash"),
        )
        _validate_basis_points(
            self.accuracy_basis_points, field="accuracy_basis_points"
        )
        _validate_basis_points(
            self.calibration_basis_points, field="calibration_basis_points"
        )
        if not isinstance(cast(object, self.is_holdout), bool):
            raise TypeError("is_holdout must be bool")
        if not (
            self.outcome_period_start
            < self.outcome_period_end
            < self.published_at
            <= self.outcome_known_at
        ):
            raise ValueError("outcome temporal ordering is invalid")
        if self.observation_id != f"decision-outcome-{self.observation_hash}":
            raise ValueError("observation_id does not match observation_hash")
        if not self.verify_integrity():
            raise ValueError("observation_hash is invalid")

    @classmethod
    def create(
        cls,
        input_: DecisionOutcomeObservationInput,
    ) -> DecisionOutcomeObservation:
        """Normalize and content-address one host-owned outcome observation."""
        digest = canonical_sha256(cls._identity_payload(input_))
        return cls(
            schema_version=1,
            observation_id=f"decision-outcome-{digest}",
            opinion_id=input_.opinion_id,
            shadow_outcome_id=input_.shadow_outcome_id,
            outcome_kind=input_.outcome_kind,
            outcome_period_start=input_.outcome_period_start,
            outcome_period_end=input_.outcome_period_end,
            outcome_known_at=input_.outcome_known_at,
            published_at=input_.published_at,
            source_snapshot_id=input_.source_snapshot_id,
            evidence_refs=input_.evidence_refs,
            adoption=input_.adoption,
            accuracy_basis_points=input_.accuracy_basis_points,
            calibration_basis_points=input_.calibration_basis_points,
            is_holdout=input_.is_holdout,
            observation_hash=digest,
        )

    @staticmethod
    def _identity_payload(
        content: DecisionOutcomeObservationInput,
    ) -> dict[str, object]:
        return {
            "schema_version": 1,
            "opinion_id": content.opinion_id,
            "shadow_outcome_id": content.shadow_outcome_id,
            "outcome_kind": content.outcome_kind,
            "outcome_period_start": content.outcome_period_start,
            "outcome_period_end": content.outcome_period_end,
            "outcome_known_at": content.outcome_known_at,
            "published_at": content.published_at,
            "source_snapshot_id": content.source_snapshot_id,
            "evidence_refs": content.evidence_refs,
            "adoption": content.adoption,
            "accuracy_basis_points": content.accuracy_basis_points,
            "calibration_basis_points": content.calibration_basis_points,
            "is_holdout": content.is_holdout,
        }

    def integrity_payload(self) -> dict[str, object]:
        """Return every field authenticated by observation_hash."""
        return self._identity_payload(
            DecisionOutcomeObservationInput(
                opinion_id=self.opinion_id,
                shadow_outcome_id=self.shadow_outcome_id,
                outcome_kind=self.outcome_kind,
                outcome_period_start=self.outcome_period_start,
                outcome_period_end=self.outcome_period_end,
                outcome_known_at=self.outcome_known_at,
                published_at=self.published_at,
                source_snapshot_id=self.source_snapshot_id,
                evidence_refs=self.evidence_refs,
                adoption=self.adoption,
                accuracy_basis_points=self.accuracy_basis_points,
                calibration_basis_points=self.calibration_basis_points,
                is_holdout=self.is_holdout,
            )
        )

    def verify_integrity(self) -> bool:
        """Recompute both observation identities."""
        return (
            canonical_sha256(self.integrity_payload()) == self.observation_hash
            and self.observation_id == f"decision-outcome-{self.observation_hash}"
        )


@dataclass(frozen=True, slots=True)
class _DecisionOutcomeFeedbackContent:
    opinion_id: str
    shadow_outcome_id: str
    opinion_hash: str
    observation_id: str
    observation_hash: str
    outcome_known_at: datetime
    linked_at: datetime
    source_snapshot_id: str
    evidence_refs: tuple[str, ...]
    adoption: DecisionOpinionAdoption
    accuracy_basis_points: int
    calibration_basis_points: int
    memory_promotion: str


@dataclass(frozen=True, slots=True)
class DecisionOutcomeFeedback:
    """Immutable linkage for outcome analysis, never a memory command."""

    schema_version: int
    feedback_id: str
    opinion_id: str
    shadow_outcome_id: str
    opinion_hash: str
    observation_id: str
    observation_hash: str
    outcome_known_at: datetime
    linked_at: datetime
    source_snapshot_id: str
    evidence_refs: tuple[str, ...]
    adoption: DecisionOpinionAdoption
    accuracy_basis_points: int
    calibration_basis_points: int
    memory_promotion: str
    feedback_hash: str

    def __post_init__(self) -> None:
        """Normalize every field and verify the closed feedback identity."""
        if self.schema_version != 1:
            raise ValueError("DecisionOutcomeFeedback schema_version must be 1")
        for field_name in (
            "feedback_id",
            "opinion_id",
            "shadow_outcome_id",
            "observation_id",
            "source_snapshot_id",
            "memory_promotion",
        ):
            object.__setattr__(
                self,
                field_name,
                normalized_text(getattr(self, field_name), field=field_name),
            )
        for field_name in (
            "opinion_hash",
            "observation_hash",
            "feedback_hash",
        ):
            object.__setattr__(
                self,
                field_name,
                sha256_hex(getattr(self, field_name), field=field_name),
            )
        for field_name in ("outcome_known_at", "linked_at"):
            object.__setattr__(
                self,
                field_name,
                utc_datetime(getattr(self, field_name), field=field_name),
            )
        object.__setattr__(
            self,
            "evidence_refs",
            normalized_unique_tuple(self.evidence_refs, field="evidence_refs"),
        )
        enum_value(self.adoption, DecisionOpinionAdoption, field="adoption")
        _validate_basis_points(
            self.accuracy_basis_points, field="accuracy_basis_points"
        )
        _validate_basis_points(
            self.calibration_basis_points, field="calibration_basis_points"
        )
        if self.memory_promotion != "none":
            raise ValueError("memory_promotion must remain none")
        if self.outcome_known_at > self.linked_at:
            raise ValueError("feedback cannot precede outcome knowledge")
        if self.feedback_id != f"decision-feedback-{self.feedback_hash}":
            raise ValueError("feedback_id does not match feedback_hash")
        if not self.verify_integrity():
            raise ValueError("feedback_hash is invalid")

    @classmethod
    def create(
        cls,
        content: _DecisionOutcomeFeedbackContent,
    ) -> DecisionOutcomeFeedback:
        """Content-address one already validated PIT linkage."""
        payload = cls._identity_payload(content)
        digest = canonical_sha256(payload)
        return cls(
            schema_version=1,
            feedback_id=f"decision-feedback-{digest}",
            opinion_id=content.opinion_id,
            shadow_outcome_id=content.shadow_outcome_id,
            opinion_hash=content.opinion_hash,
            observation_id=content.observation_id,
            observation_hash=content.observation_hash,
            outcome_known_at=content.outcome_known_at,
            linked_at=content.linked_at,
            source_snapshot_id=content.source_snapshot_id,
            evidence_refs=content.evidence_refs,
            adoption=content.adoption,
            accuracy_basis_points=content.accuracy_basis_points,
            calibration_basis_points=content.calibration_basis_points,
            memory_promotion=content.memory_promotion,
            feedback_hash=digest,
        )

    @staticmethod
    def _identity_payload(
        content: _DecisionOutcomeFeedbackContent,
    ) -> dict[str, object]:
        return {
            "schema_version": 1,
            "opinion_id": content.opinion_id,
            "shadow_outcome_id": content.shadow_outcome_id,
            "opinion_hash": content.opinion_hash,
            "observation_id": content.observation_id,
            "observation_hash": content.observation_hash,
            "outcome_known_at": content.outcome_known_at,
            "linked_at": content.linked_at,
            "source_snapshot_id": content.source_snapshot_id,
            "evidence_refs": content.evidence_refs,
            "adoption": content.adoption,
            "accuracy_basis_points": content.accuracy_basis_points,
            "calibration_basis_points": content.calibration_basis_points,
            "memory_promotion": content.memory_promotion,
        }

    def integrity_payload(self) -> dict[str, object]:
        """Return every field authenticated by feedback_hash."""
        return self._identity_payload(
            _DecisionOutcomeFeedbackContent(
                opinion_id=self.opinion_id,
                shadow_outcome_id=self.shadow_outcome_id,
                opinion_hash=self.opinion_hash,
                observation_id=self.observation_id,
                observation_hash=self.observation_hash,
                outcome_known_at=self.outcome_known_at,
                linked_at=self.linked_at,
                source_snapshot_id=self.source_snapshot_id,
                evidence_refs=self.evidence_refs,
                adoption=self.adoption,
                accuracy_basis_points=self.accuracy_basis_points,
                calibration_basis_points=self.calibration_basis_points,
                memory_promotion=self.memory_promotion,
            )
        )

    def verify_integrity(self) -> bool:
        """Verify the closed feedback identity."""
        return (
            self.schema_version == 1
            and self.memory_promotion == "none"
            and canonical_sha256(self.integrity_payload()) == self.feedback_hash
            and self.feedback_id == f"decision-feedback-{self.feedback_hash}"
        )


class DecisionOutcomeLinker:
    """Link only host-known, non-holdout outcomes to immutable opinions."""

    def link(
        self,
        *,
        opinion: DecisionOpinionRecord,
        observation: DecisionOutcomeObservation,
        context: EvidenceTemporalContext,
        linked_at: datetime,
    ) -> DecisionOutcomeFeedback:
        """Create feedback after every PIT and identity boundary is proven."""
        linked_at = utc_datetime(linked_at, field="linked_at")
        if not _valid_opinion(opinion):
            raise _feedback_error(
                "DecisionOpinion identity is invalid",
                "decision_outcome_opinion_invalid",
            )
        if not observation.verify_integrity() or (
            observation.opinion_id,
            observation.shadow_outcome_id,
        ) != (opinion.opinion_id, opinion.shadow_outcome_id):
            raise _feedback_error(
                "Outcome observation is not bound to the opinion",
                "decision_outcome_identity_mismatch",
            )
        if observation.is_holdout:
            raise _feedback_error(
                "Holdout outcomes cannot enter shadow feedback",
                "decision_outcome_holdout_forbidden",
            )
        if observation.outcome_period_start <= opinion.generated_at:
            raise _feedback_error(
                "Outcome window must start after opinion generation",
                "decision_outcome_window_invalid",
            )
        if observation.outcome_known_at > context.knowledge_cutoff:
            raise _feedback_error(
                "Outcome is not visible at the knowledge cutoff",
                "decision_outcome_not_yet_known",
            )
        if observation.published_at > context.publication_cutoff:
            raise _feedback_error(
                "Outcome is not visible at the publication cutoff",
                "decision_outcome_not_yet_published",
            )
        if observation.source_snapshot_id != context.source_snapshot_id:
            raise _feedback_error(
                "Outcome snapshot differs from the host context",
                "decision_outcome_snapshot_mismatch",
            )
        if not (observation.outcome_known_at <= linked_at <= context.decision_time):
            raise _feedback_error(
                "Feedback link time is outside the host context",
                "decision_outcome_link_time_invalid",
            )
        return DecisionOutcomeFeedback.create(
            _DecisionOutcomeFeedbackContent(
                opinion_id=opinion.opinion_id,
                shadow_outcome_id=opinion.shadow_outcome_id,
                opinion_hash=opinion.opinion_hash,
                observation_id=observation.observation_id,
                observation_hash=observation.observation_hash,
                outcome_known_at=observation.outcome_known_at,
                linked_at=linked_at,
                source_snapshot_id=observation.source_snapshot_id,
                evidence_refs=observation.evidence_refs,
                adoption=observation.adoption,
                accuracy_basis_points=observation.accuracy_basis_points,
                calibration_basis_points=observation.calibration_basis_points,
                memory_promotion="none",
            )
        )


def _validate_basis_points(value: int, *, field: str) -> None:
    raw = cast(object, value)
    if isinstance(raw, bool) or not isinstance(raw, int):
        raise TypeError(f"{field} must be an integer")
    if not 0 <= value <= _BASIS_POINTS:
        raise ValueError(f"{field} must be between 0 and 10000")


def _valid_opinion(opinion: DecisionOpinionRecord) -> bool:
    payload = {
        "schema_version": opinion.schema_version,
        "status": opinion.status,
        "v3_artifact_id": opinion.v3_artifact_id,
        "v3_evidence_hash": opinion.v3_evidence_hash,
        "v3_readiness": opinion.v3_readiness,
        "summary": opinion.summary,
        "dissent": opinion.dissent,
        "uncertainty": opinion.uncertainty,
        "evidence_refs": opinion.evidence_refs,
        "blocking_reasons": opinion.blocking_reasons,
        "reason_code": opinion.reason_code,
        "model_profile": opinion.model_profile,
        "prompt_hash": opinion.prompt_hash,
        "provider_id": opinion.provider_id,
        "generated_at": opinion.generated_at,
    }
    return (
        opinion.schema_version == 1
        and canonical_sha256(payload) == opinion.opinion_hash
        and opinion.opinion_id == f"decision-opinion-{opinion.opinion_hash}"
        and opinion.shadow_outcome_id == f"decision-shadow-{opinion.opinion_hash}"
    )


def _feedback_error(message: str, reason_code: str) -> DecisionOutcomeFeedbackError:
    return DecisionOutcomeFeedbackError(message, reason_code=reason_code)


__all__ = [
    "DecisionOpinionAdoption",
    "DecisionOutcomeFeedback",
    "DecisionOutcomeFeedbackError",
    "DecisionOutcomeLinker",
    "DecisionOutcomeObservation",
    "DecisionOutcomeObservationInput",
]
