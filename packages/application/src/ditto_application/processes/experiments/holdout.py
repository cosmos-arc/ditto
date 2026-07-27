"""Application orchestration for one atomic pre-holdout candidate claim."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import NoReturn, Protocol, cast

from ditto_application.exceptions import AppProcessError
from ditto_application.processes.experiments._holdout_contract import (
    HoldoutClaimPersistenceRequest,
    PersistedHoldoutClaim,
)
from ditto_application.processes.experiments._selection_evidence_artifact import (
    PublishedSelectionEvidence,
)
from ditto_application.processes.experiments.scheduler_store import (
    CandidateId,
    ContentHash,
    ExperimentId,
    ExperimentLaunchSpec,
    FirstAttempt,
    FirstAttemptFactory,
    FoldView,
    SchedulerLease,
)
from ditto_application.processes.experiments.trial_evidence_bridge import (
    verify_pre_holdout_selection_evidence,
)

__all__ = [
    "ClaimHoldoutCandidateRequest",
    "HoldoutClaimProcess",
    "HoldoutClaimReceipt",
    "HoldoutSelectionEvidenceProvider",
    "HoldoutSelectionReason",
]

_MISSING = object()
_SHA256_HEX_LENGTH = 64


def _holdout_error(reason: str, **details: object) -> NoReturn:
    raise AppProcessError(
        "holdout candidate claim is invalid",
        details={"code": "SPEC_INVALID", "reason": reason, **details},
    )


def _canonical_text(value: object, field_name: str) -> str:
    if type(value) is not str or not value or value != value.strip():
        _holdout_error("holdout_claim_text_invalid", field=field_name)
    return value


def _content_hash(value: object, field_name: str) -> ContentHash:
    if (
        type(value) is not str
        or len(value) != _SHA256_HEX_LENGTH
        or any(character not in "0123456789abcdef" for character in value)
    ):
        _holdout_error("holdout_claim_hash_invalid", field=field_name)
    return ContentHash(value)


def _require_utc(value: object, field_name: str) -> datetime:
    if (
        type(value) is not datetime
        or value.tzinfo is None
        or value.utcoffset() != timedelta(0)
    ):
        _holdout_error("holdout_claim_time_must_be_utc", field=field_name)
    return value


@dataclass(frozen=True, slots=True)
class HoldoutSelectionReason:
    """Typed operator rationale bound into the immutable claim request."""

    code: str
    summary: str

    def __post_init__(self) -> None:
        """Reject blank or whitespace-dependent rationale."""
        _canonical_text(cast("object", self.code), "selection_reason.code")
        _canonical_text(cast("object", self.summary), "selection_reason.summary")


@dataclass(frozen=True, slots=True)
class ClaimHoldoutCandidateRequest:
    """Only caller-authored inputs allowed at the holdout authority boundary."""

    experiment_id: str
    candidate_id: str
    expected_revision: int
    expected_selection_evidence_hash: str
    operator_confirmation: str
    selection_reason: HoldoutSelectionReason
    occurred_at: datetime

    def __post_init__(self) -> None:
        """Validate canonical request values without accepting derived identity."""
        _canonical_text(cast("object", self.experiment_id), "experiment_id")
        _canonical_text(cast("object", self.candidate_id), "candidate_id")
        if type(self.expected_revision) is not int or self.expected_revision < 0:
            _holdout_error("holdout_claim_revision_invalid")
        _content_hash(
            cast("object", self.expected_selection_evidence_hash),
            "expected_selection_evidence_hash",
        )
        _canonical_text(
            cast("object", self.operator_confirmation),
            "operator_confirmation",
        )
        if type(self.selection_reason) is not HoldoutSelectionReason:
            _holdout_error("holdout_selection_reason_invalid")
        _require_utc(cast("object", self.occurred_at), "occurred_at")


@dataclass(frozen=True, slots=True)
class HoldoutClaimReceipt:
    """Committed server truth returned by the atomic claim transaction."""

    claim_id: str
    experiment_id: str
    candidate_id: str
    fold_id: str
    logical_run_id: str
    reproduction_fingerprint: str
    claim_payload_hash: str
    selection_evidence_hash: str
    experiment_revision: int
    event_id: str
    occurred_at: datetime

    def __post_init__(self) -> None:
        """Reject malformed persistence acknowledgements at the app boundary."""
        for field_name in (
            "claim_id",
            "experiment_id",
            "candidate_id",
            "fold_id",
            "logical_run_id",
            "event_id",
        ):
            _canonical_text(cast("object", getattr(self, field_name)), field_name)
        for field_name in (
            "reproduction_fingerprint",
            "claim_payload_hash",
            "selection_evidence_hash",
        ):
            _content_hash(cast("object", getattr(self, field_name)), field_name)
        if type(self.experiment_revision) is not int or self.experiment_revision < 0:
            _holdout_error("holdout_claim_receipt_revision_invalid")
        _require_utc(cast("object", self.occurred_at), "occurred_at")


class HoldoutSelectionEvidenceProvider(Protocol):
    """Read the immutable Task 11 trial ledger selected by an operator."""

    def read_selection_evidence(
        self,
        experiment_id: ExperimentId,
        expected_content_hash: ContentHash,
    ) -> PublishedSelectionEvidence:
        """Return the exact content-addressed selection artifact and ledger."""
        ...


class _HoldoutSchedulerSnapshot(Protocol):
    @property
    def launch_spec(self) -> ExperimentLaunchSpec: ...

    @property
    def folds(self) -> tuple[FoldView, ...]: ...

    @property
    def holdout_claim(self) -> PersistedHoldoutClaim | None: ...


class _HoldoutClaimStore(Protocol):
    def load_snapshot(self, experiment_id: ExperimentId) -> _HoldoutSchedulerSnapshot:
        """Load one authoritative scheduler snapshot."""
        ...

    def claim_holdout_candidate(
        self,
        request: HoldoutClaimPersistenceRequest,
        *,
        lease: SchedulerLease | None,
        now_epoch_us: int | None,
    ) -> PersistedHoldoutClaim:
        """Persist or exactly replay the atomic holdout claim."""
        ...


class HoldoutClaimProcess:
    """Verify selection evidence and resolve execution identity before commit."""

    def __init__(
        self,
        *,
        store: _HoldoutClaimStore,
        first_attempt_factory: FirstAttemptFactory,
        selection_evidence_provider: HoldoutSelectionEvidenceProvider | None,
    ) -> None:
        self._store = store
        self._first_attempt_factory = first_attempt_factory
        self._selection_evidence_provider = selection_evidence_provider

    def claim_candidate(
        self,
        request: ClaimHoldoutCandidateRequest,
        *,
        lease: SchedulerLease | None,
        now_epoch_us: int | None,
    ) -> HoldoutClaimReceipt:
        """Persist one claim; replay it without consulting moving dependencies."""
        if type(request) is not ClaimHoldoutCandidateRequest:
            _holdout_error("holdout_claim_request_invalid")
        experiment_id = ExperimentId(request.experiment_id)
        candidate_id = CandidateId(request.candidate_id)
        evidence_hash = ContentHash(request.expected_selection_evidence_hash)
        snapshot = self._store.load_snapshot(experiment_id)
        existing = getattr(snapshot, "holdout_claim", _MISSING)
        if existing is _MISSING:
            _holdout_error("holdout_claim_snapshot_contract_invalid")
        if existing is not None:
            return self.replay_candidate(request)
        if (
            type(lease) is not SchedulerLease
            or lease.experiment_id != experiment_id
            or type(now_epoch_us) is not int
            or now_epoch_us < 0
        ):
            _holdout_error("holdout_claim_authority_required")
        provider = self._selection_evidence_provider
        if provider is None:
            _holdout_error("selection_evidence_provider_unavailable")
        published = provider.read_selection_evidence(experiment_id, evidence_hash)
        if type(published) is not PublishedSelectionEvidence:
            _holdout_error("selection_evidence_provider_contract_invalid")
        if request.occurred_at < published.record.created_at:
            _holdout_error(
                "holdout_claim_precedes_selection_evidence",
                selection_evidence_created_at=published.record.created_at.isoformat(),
            )
        verified = verify_pre_holdout_selection_evidence(
            published.ledger,
            launch_spec=snapshot.launch_spec,
            experiment_id=experiment_id,
            candidate_id=candidate_id,
            expected_content_hash=evidence_hash,
        )
        fold = self._selected_holdout_fold(
            snapshot,
            experiment_id=experiment_id,
            candidate_id=candidate_id,
        )
        first_attempt = self._first_attempt_factory.create(fold, request.occurred_at)
        if (
            type(first_attempt) is not FirstAttempt
            or first_attempt.spec.fold_key != fold.spec.key
            or type(first_attempt.spec.reproduction_fingerprint) is not ContentHash
        ):
            _holdout_error("holdout_first_attempt_contract_invalid")
        return self._persist(
            request,
            experiment_id=experiment_id,
            candidate_id=candidate_id,
            evidence_hash=verified.content_hash,
            reproduction_fingerprint=first_attempt.spec.reproduction_fingerprint,
            lease=lease,
            now_epoch_us=now_epoch_us,
        )

    def replay_candidate(
        self,
        request: ClaimHoldoutCandidateRequest,
    ) -> HoldoutClaimReceipt:
        """Probe persisted authority without a lease or moving dependencies."""
        if type(request) is not ClaimHoldoutCandidateRequest:
            _holdout_error("holdout_claim_request_invalid")
        return self._persist(
            request,
            experiment_id=ExperimentId(request.experiment_id),
            candidate_id=CandidateId(request.candidate_id),
            evidence_hash=ContentHash(request.expected_selection_evidence_hash),
            reproduction_fingerprint=None,
            lease=None,
            now_epoch_us=None,
        )

    @staticmethod
    def _selected_holdout_fold(
        snapshot: _HoldoutSchedulerSnapshot,
        *,
        experiment_id: ExperimentId,
        candidate_id: CandidateId,
    ) -> FoldView:
        raw_folds: object = getattr(snapshot, "folds", _MISSING)
        if type(raw_folds) is not tuple:
            _holdout_error("holdout_claim_snapshot_contract_invalid")
        folds = cast("tuple[object, ...]", raw_folds)
        selected = tuple(
            fold
            for fold in folds
            if type(fold) is FoldView
            and fold.spec.key.experiment_id == experiment_id
            and fold.spec.key.candidate_id == candidate_id
            and fold.spec.fold_role.value == "holdout"
        )
        if len(selected) != 1:
            _holdout_error(
                "holdout_fold_not_unique",
                matching_fold_count=len(selected),
            )
        return selected[0]

    def _persist(
        self,
        request: ClaimHoldoutCandidateRequest,
        *,
        experiment_id: ExperimentId,
        candidate_id: CandidateId,
        evidence_hash: ContentHash,
        reproduction_fingerprint: ContentHash | None,
        lease: SchedulerLease | None,
        now_epoch_us: int | None,
    ) -> HoldoutClaimReceipt:
        persistence_request = HoldoutClaimPersistenceRequest(
            experiment_id=str(experiment_id),
            candidate_id=str(candidate_id),
            expected_revision=request.expected_revision,
            expected_selection_evidence_hash=str(evidence_hash),
            operator_confirmation=request.operator_confirmation,
            selection_reason_code=request.selection_reason.code,
            selection_reason_summary=request.selection_reason.summary,
            resolved_reproduction_fingerprint=(
                None
                if reproduction_fingerprint is None
                else str(reproduction_fingerprint)
            ),
            occurred_at=request.occurred_at,
        )
        persisted = self._store.claim_holdout_candidate(
            persistence_request,
            lease=lease,
            now_epoch_us=now_epoch_us,
        )
        return HoldoutClaimReceipt(
            claim_id=persisted.claim_id,
            experiment_id=str(persisted.experiment_id),
            candidate_id=str(persisted.candidate_id),
            fold_id=str(persisted.fold_id),
            logical_run_id=persisted.logical_run_id,
            reproduction_fingerprint=str(persisted.reproduction_fingerprint),
            claim_payload_hash=str(persisted.claim_payload_hash),
            selection_evidence_hash=str(persisted.selection_evidence_hash),
            experiment_revision=persisted.experiment_revision,
            event_id=persisted.event_id,
            occurred_at=persisted.claimed_at,
        )
