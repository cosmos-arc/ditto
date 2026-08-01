"""Application orchestration for one atomic pre-holdout candidate claim."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import NoReturn, Protocol, cast

from ditto_application.candidate_selection import CandidateSelectionReceipt
from ditto_application.exceptions import AppProcessError
from ditto_application.mutation_idempotency import (
    MutationIdempotency,
    find_mutation_fence,
    mutation_fence_detail,
)
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


def _holdout_already_claimed(**details: object) -> NoReturn:
    raise AppProcessError(
        "holdout candidate has already been claimed",
        details={
            "code": "HOLDOUT_ALREADY_CLAIMED",
            "reason": "holdout_already_claimed",
            **details,
        },
    )


def _holdout_selection_error(
    code: str,
    reason: str,
    **details: object,
) -> NoReturn:
    raise AppProcessError(
        "holdout candidate selection evidence is invalid",
        details={"code": code, "reason": reason, **details},
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
    selection_id: str | None = None
    expected_candidate_evidence_content_hash: str | None = None
    idempotency: MutationIdempotency | None = None

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
        optional = (
            self.selection_id,
            self.expected_candidate_evidence_content_hash,
            self.idempotency,
        )
        if any(value is not None for value in optional):
            if self.selection_id is None:
                _holdout_error("holdout_selection_id_required")
            _canonical_text(self.selection_id, "selection_id")
            if self.expected_candidate_evidence_content_hash is None:
                _holdout_error("holdout_candidate_evidence_hash_required")
            _content_hash(
                self.expected_candidate_evidence_content_hash,
                "expected_candidate_evidence_content_hash",
            )
            if type(self.idempotency) is not MutationIdempotency:
                _holdout_error("holdout_idempotency_required")


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
    selection_id: str | None = None
    candidate_evidence_content_hash: str | None = None

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
        if self.selection_id is not None:
            _canonical_text(cast("object", self.selection_id), "selection_id")
        if self.candidate_evidence_content_hash is not None:
            _content_hash(
                cast("object", self.candidate_evidence_content_hash),
                "candidate_evidence_content_hash",
            )


class HoldoutSelectionEvidenceProvider(Protocol):
    """Read the immutable Task 11 trial ledger selected by an operator."""

    def read_selection_evidence(
        self,
        experiment_id: ExperimentId,
        expected_content_hash: ContentHash,
    ) -> PublishedSelectionEvidence:
        """Return the exact content-addressed selection artifact and ledger."""
        ...


class HoldoutCandidateSelectionProvider(Protocol):
    """Read the durable preselection event required by the HTTP holdout path."""

    def read_selection(
        self,
        experiment_id: str,
        selection_id: str,
    ) -> CandidateSelectionReceipt | None: ...


class _HoldoutSchedulerSnapshot(Protocol):
    @property
    def launch_spec(self) -> ExperimentLaunchSpec: ...

    @property
    def folds(self) -> tuple[FoldView, ...]: ...

    @property
    def holdout_claim(self) -> PersistedHoldoutClaim | None: ...


class _StatusEvent(Protocol):
    @property
    def detail(self) -> Mapping[str, object]: ...


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

    def list_status_events(
        self,
        experiment_id: ExperimentId,
    ) -> tuple[_StatusEvent, ...]: ...


class HoldoutClaimProcess:
    """Verify selection evidence and resolve execution identity before commit."""

    def __init__(
        self,
        *,
        store: _HoldoutClaimStore,
        first_attempt_factory: FirstAttemptFactory,
        selection_evidence_provider: HoldoutSelectionEvidenceProvider | None,
        candidate_selection_provider: HoldoutCandidateSelectionProvider | None = None,
    ) -> None:
        self._store = store
        self._first_attempt_factory = first_attempt_factory
        self._selection_evidence_provider = selection_evidence_provider
        self._candidate_selection_provider = candidate_selection_provider

    def claim_candidate(  # noqa: C901
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
        replay = self._idempotent_replay(request, experiment_id)
        if replay is not None:
            return replay
        snapshot = self._store.load_snapshot(experiment_id)
        existing = getattr(snapshot, "holdout_claim", _MISSING)
        if existing is _MISSING:
            _holdout_error("holdout_claim_snapshot_contract_invalid")
        if existing is not None:
            persisted_existing = cast("PersistedHoldoutClaim", existing)
            if request.idempotency is not None:
                _holdout_already_claimed(
                    experiment_id=request.experiment_id,
                    candidate_id=str(persisted_existing.candidate_id),
                )
            return self.replay_candidate(request)
        self._verify_candidate_selection(request)
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
            event_detail_extension=(
                None
                if request.idempotency is None
                else mutation_fence_detail(request.idempotency)
            ),
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
            selection_id=request.selection_id,
            candidate_evidence_content_hash=(
                request.expected_candidate_evidence_content_hash
            ),
        )

    def _verify_candidate_selection(
        self,
        request: ClaimHoldoutCandidateRequest,
    ) -> None:
        """Verify the optional HTTP preselection contract before claim authority."""
        if request.selection_id is None:
            return
        provider = self._candidate_selection_provider
        if provider is None:
            _holdout_error("candidate_selection_provider_unavailable")
        selected = provider.read_selection(request.experiment_id, request.selection_id)
        if selected is None:
            _holdout_selection_error(
                "CANDIDATE_NOT_PRESELECTED",
                "candidate_not_preselected",
            )
        if (
            selected.candidate_id != request.candidate_id
            or selected.selection_evidence_content_hash
            != request.expected_selection_evidence_hash
            or selected.candidate_evidence_content_hash
            != request.expected_candidate_evidence_content_hash
            or selected.experiment_revision != request.expected_revision
            or request.occurred_at < selected.occurred_at
        ):
            _holdout_selection_error(
                "EVIDENCE_STALE",
                "candidate_selection_evidence_stale",
            )

    def _idempotent_replay(
        self,
        request: ClaimHoldoutCandidateRequest,
        experiment_id: ExperimentId,
    ) -> HoldoutClaimReceipt | None:
        identity = request.idempotency
        if identity is None:
            return None
        events = self._store.list_status_events(experiment_id)
        if not find_mutation_fence(
            tuple(event.detail for event in events),
            identity,
        ):
            return None
        snapshot = self._store.load_snapshot(experiment_id)
        persisted = snapshot.holdout_claim
        if (
            persisted is None
            or persisted.candidate_id != request.candidate_id
            or persisted.selection_evidence_hash
            != request.expected_selection_evidence_hash
        ):
            _holdout_error("holdout_idempotency_replay_drift")
        return HoldoutClaimReceipt(
            claim_id=persisted.claim_id,
            experiment_id=persisted.experiment_id,
            candidate_id=persisted.candidate_id,
            fold_id=persisted.fold_id,
            logical_run_id=persisted.logical_run_id,
            reproduction_fingerprint=persisted.reproduction_fingerprint,
            claim_payload_hash=persisted.claim_payload_hash,
            selection_evidence_hash=persisted.selection_evidence_hash,
            experiment_revision=persisted.experiment_revision,
            event_id=persisted.event_id,
            occurred_at=persisted.claimed_at,
            selection_id=request.selection_id,
            candidate_evidence_content_hash=(
                request.expected_candidate_evidence_content_hash
            ),
        )
