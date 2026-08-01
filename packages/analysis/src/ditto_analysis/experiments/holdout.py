"""Immutable authority contracts for one-shot holdout selection."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import cast

from ditto_analysis.errors import ExperimentSpecError
from ditto_analysis.experiments._validation import require_utc_datetime
from ditto_analysis.experiments.models import CandidateId, ContentHash, ExperimentId
from ditto_analysis.experiments.persistence import HoldoutClaimRecord

__all__ = [
    "AtomicHoldoutClaimReceipt",
    "HoldoutClaimAuthorityCommand",
    "HoldoutSelectionReason",
    "holdout_request_payload",
]


def _holdout_error(
    message: str,
    reason_code: str,
    **details: object,
) -> ExperimentSpecError:
    return ExperimentSpecError(
        message,
        details={"reason_code": reason_code, **details},
    )


def _canonical_text(value: object, field_name: str) -> str:
    if type(value) is not str or not value or value != value.strip():
        raise _holdout_error(
            f"{field_name} must be a non-empty canonical string",
            "invalid_holdout_claim_text",
            field=field_name,
        )
    return value


@dataclass(frozen=True, slots=True)
class HoldoutSelectionReason:
    """Typed operator rationale bound into the immutable claim request."""

    code: str
    summary: str

    def __post_init__(self) -> None:
        """Reject blank or whitespace-dependent reason values."""
        _canonical_text(cast("object", self.code), "selection_reason.code")
        _canonical_text(cast("object", self.summary), "selection_reason.summary")


@dataclass(frozen=True, slots=True)
class HoldoutClaimAuthorityCommand:
    """Trusted inputs for the atomic one-shot holdout claim transaction."""

    experiment_id: ExperimentId
    candidate_id: CandidateId
    expected_revision: int
    expected_selection_evidence_hash: ContentHash
    operator_confirmation: str
    selection_reason: HoldoutSelectionReason
    resolved_reproduction_fingerprint: ContentHash | None
    occurred_at: datetime
    event_detail_extension: Mapping[str, object] | None = None

    def __post_init__(self) -> None:
        """Require exact nominal identities and canonical operator input."""
        if type(self.experiment_id) is not ExperimentId:
            raise _holdout_error(
                "experiment_id must be an exact ExperimentId",
                "invalid_holdout_experiment_id",
            )
        if type(self.candidate_id) is not CandidateId:
            raise _holdout_error(
                "candidate_id must be an exact CandidateId",
                "invalid_holdout_candidate_id",
            )
        if type(self.expected_revision) is not int or self.expected_revision < 0:
            raise _holdout_error(
                "expected_revision must be a non-negative integer",
                "invalid_holdout_expected_revision",
            )
        if type(self.expected_selection_evidence_hash) is not ContentHash:
            raise _holdout_error(
                "expected_selection_evidence_hash must be a ContentHash",
                "invalid_holdout_selection_evidence_hash",
            )
        _canonical_text(
            cast("object", self.operator_confirmation),
            "operator_confirmation",
        )
        if type(self.selection_reason) is not HoldoutSelectionReason:
            raise _holdout_error(
                "selection_reason must be a HoldoutSelectionReason",
                "invalid_holdout_selection_reason",
            )
        if (
            self.resolved_reproduction_fingerprint is not None
            and type(self.resolved_reproduction_fingerprint) is not ContentHash
        ):
            raise _holdout_error(
                "resolved_reproduction_fingerprint must be a ContentHash or None",
                "invalid_holdout_reproduction_fingerprint",
            )
        require_utc_datetime(cast("object", self.occurred_at), "occurred_at")
        if self.event_detail_extension is not None and not isinstance(
            cast("object", self.event_detail_extension),
            Mapping,
        ):
            raise _holdout_error(
                "event_detail_extension must be a mapping or None",
                "invalid_holdout_event_detail_extension",
            )


@dataclass(frozen=True, slots=True)
class AtomicHoldoutClaimReceipt:
    """Durable claim plus the single transaction's experiment event identity."""

    claim: HoldoutClaimRecord
    experiment_revision: int
    event_id: str

    def __post_init__(self) -> None:
        """Reject malformed persistence acknowledgements at the adapter boundary."""
        if type(self.claim) is not HoldoutClaimRecord:
            raise _holdout_error(
                "claim must be a HoldoutClaimRecord",
                "invalid_holdout_claim_receipt",
            )
        if type(self.experiment_revision) is not int or self.experiment_revision < 0:
            raise _holdout_error(
                "experiment_revision must be a non-negative integer",
                "invalid_holdout_claim_receipt",
            )
        _canonical_text(cast("object", self.event_id), "event_id")


def holdout_request_payload(
    command: HoldoutClaimAuthorityCommand,
) -> dict[str, object]:
    """Return the canonical caller-authored portion of a holdout claim."""
    if type(command) is not HoldoutClaimAuthorityCommand:
        raise _holdout_error(
            "command must be a HoldoutClaimAuthorityCommand",
            "invalid_holdout_claim_command",
        )
    return {
        "schema_version": 1,
        "expected_experiment_revision": command.expected_revision,
        "expected_selection_evidence_hash": str(
            command.expected_selection_evidence_hash
        ),
        "reason": {
            "code": command.selection_reason.code,
            "summary": command.selection_reason.summary,
        },
    }
