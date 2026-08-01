"""Neutral contracts for durable candidate preselection coordination."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import NoReturn

from ditto_application.exceptions import AppProcessError
from ditto_application.mutation_idempotency import MutationIdempotency

__all__ = ["CandidateSelectionReceipt", "CandidateSelectionRequest"]

_HASH_LENGTH = 64


def _error(code: str, reason: str, message: str, **details: object) -> NoReturn:
    raise AppProcessError(
        message,
        details={"code": code, "reason": reason, **details},
    )


def _text(value: object, *, field: str) -> str:
    if type(value) is not str or not value or value != value.strip():
        _error(
            "CANDIDATE_NOT_ELIGIBLE",
            "candidate_selection_input_invalid",
            "candidate selection input is invalid",
            field=field,
        )
    return value


def _hash(value: object, *, field: str) -> str:
    text = _text(value, field=field)
    if len(text) != _HASH_LENGTH or any(
        character not in "0123456789abcdef" for character in text
    ):
        _error(
            "CANDIDATE_NOT_ELIGIBLE",
            "candidate_selection_hash_invalid",
            "candidate selection hash is invalid",
            field=field,
        )
    return text


def _utc(value: object) -> datetime:
    if (
        type(value) is not datetime
        or value.tzinfo is None
        or value.utcoffset() != timedelta(0)
    ):
        _error(
            "CANDIDATE_NOT_ELIGIBLE",
            "candidate_selection_time_invalid",
            "candidate selection time must be UTC",
        )
    return value


@dataclass(frozen=True, slots=True)
class CandidateSelectionRequest:
    """Exact caller identity for one server-side promotion preselection."""

    experiment_id: str
    candidate_id: str
    comparison_payload_hash: str
    expected_revision: int
    rationale: str
    occurred_at: datetime
    idempotency: MutationIdempotency

    def __post_init__(self) -> None:
        """Validate exact candidate, comparison, revision, and operator inputs."""
        _text(self.experiment_id, field="experiment_id")
        _text(self.candidate_id, field="candidate_id")
        _hash(self.comparison_payload_hash, field="comparison_payload_hash")
        _text(self.rationale, field="rationale")
        _utc(self.occurred_at)
        if type(self.expected_revision) is not int or self.expected_revision < 0:
            _error(
                "CANDIDATE_NOT_ELIGIBLE",
                "candidate_selection_revision_invalid",
                "candidate selection revision is invalid",
            )
        if type(self.idempotency) is not MutationIdempotency:
            _error(
                "CANDIDATE_NOT_ELIGIBLE",
                "candidate_selection_idempotency_invalid",
                "candidate selection idempotency identity is invalid",
            )


@dataclass(frozen=True, slots=True)
class CandidateSelectionReceipt:
    """Committed selection event and all immutable evidence identities."""

    selection_id: str
    experiment_id: str
    candidate_id: str
    comparison_payload_hash: str
    candidate_evidence_artifact_id: str
    candidate_evidence_content_hash: str
    selection_evidence_content_hash: str
    experiment_revision: int
    event_id: str
    occurred_at: datetime

    def __post_init__(self) -> None:
        """Validate the immutable committed receipt projection."""
        for field in (
            "selection_id",
            "experiment_id",
            "candidate_id",
            "candidate_evidence_artifact_id",
            "event_id",
        ):
            _text(getattr(self, field), field=field)
        for field in (
            "comparison_payload_hash",
            "candidate_evidence_content_hash",
            "selection_evidence_content_hash",
        ):
            _hash(getattr(self, field), field=field)
        if type(self.experiment_revision) is not int or self.experiment_revision < 0:
            _error(
                "CANDIDATE_SELECTION_CONFLICT",
                "candidate_selection_receipt_invalid",
                "candidate selection receipt is invalid",
            )
        _utc(self.occurred_at)

    def canonical_response(self) -> dict[str, object]:
        """Return the durable replay payload embedded in the status event."""
        return {
            "candidate_evidence_artifact_id": self.candidate_evidence_artifact_id,
            "candidate_evidence_content_hash": self.candidate_evidence_content_hash,
            "candidate_id": self.candidate_id,
            "comparison_payload_hash": self.comparison_payload_hash,
            "event_id": self.event_id,
            "experiment_id": self.experiment_id,
            "experiment_revision": self.experiment_revision,
            "occurred_at": self.occurred_at.isoformat(),
            "selection_evidence_content_hash": self.selection_evidence_content_hash,
            "selection_id": self.selection_id,
        }
