"""Application-local durable holdout claim projection."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from ditto_application.mutation_idempotency import (
    without_validated_mutation_fence,
)
from ditto_application.processes.experiments._process_error import (
    experiment_process_error,
)


class _FoldKey(Protocol):
    @property
    def experiment_id(self) -> object: ...

    @property
    def candidate_id(self) -> object: ...

    @property
    def fold_id(self) -> object: ...


class _DateValue(Protocol):
    def isoformat(self) -> str: ...


class _Window(Protocol):
    @property
    def start(self) -> _DateValue: ...

    @property
    def end(self) -> _DateValue: ...


class StorageHoldoutClaim(Protocol):
    """Read-only structural view of the analysis-owned claim fact."""

    @property
    def claim_id(self) -> str: ...

    @property
    def fold_key(self) -> _FoldKey: ...

    @property
    def logical_run_id(self) -> str: ...

    @property
    def reproduction_fingerprint(self) -> object: ...

    @property
    def resolved_spec_hash(self) -> object: ...

    @property
    def parameters_hash(self) -> object: ...

    @property
    def snapshot_id(self) -> object: ...

    @property
    def window(self) -> _Window: ...

    @property
    def claim_payload_hash(self) -> object: ...

    @property
    def operator_confirmation(self) -> str: ...

    @property
    def selection_reason(self) -> Mapping[str, object]: ...

    @property
    def claimed_at(self) -> datetime: ...


class StorageStatusEvent(Protocol):
    """Structural status-event facts needed to rehydrate one claim receipt."""

    @property
    def event_id(self) -> str: ...

    @property
    def experiment_id(self) -> object: ...

    @property
    def candidate_id(self) -> object | None: ...

    @property
    def fold_id(self) -> object | None: ...

    @property
    def attempt_id(self) -> object | None: ...

    @property
    def subject_type(self) -> object: ...

    @property
    def subject_revision(self) -> int: ...

    @property
    def previous_status(self) -> object | None: ...

    @property
    def status(self) -> object: ...

    @property
    def desired_state(self) -> object | None: ...

    @property
    def stage(self) -> object | None: ...

    @property
    def failure_code(self) -> object | None: ...

    @property
    def reason_code(self) -> str | None: ...

    @property
    def detail(self) -> Mapping[str, object]: ...

    @property
    def occurred_at(self) -> datetime: ...


@dataclass(frozen=True, slots=True)
class HoldoutClaimPersistenceRequest:
    """One bounded application request for the atomic persistence port."""

    experiment_id: str
    candidate_id: str
    expected_revision: int
    expected_selection_evidence_hash: str
    operator_confirmation: str
    selection_reason_code: str
    selection_reason_summary: str
    resolved_reproduction_fingerprint: str | None
    occurred_at: datetime
    event_detail_extension: Mapping[str, object] | None = None


@dataclass(frozen=True, slots=True)
class PersistedHoldoutClaim:
    """Flat committed claim truth returned by the scheduler store facade."""

    claim_id: str
    experiment_id: str
    candidate_id: str
    fold_id: str
    logical_run_id: str
    reproduction_fingerprint: str
    claim_payload_hash: str
    selection_evidence_hash: str
    resolved_spec_hash: str
    parameters_hash: str
    snapshot_id: str
    window_start: str
    window_end: str
    experiment_revision: int
    event_id: str
    claimed_at: datetime


def persisted_holdout_claim(
    claim: StorageHoldoutClaim,
    *,
    experiment_revision: int,
    event_id: str,
) -> PersistedHoldoutClaim:
    """Flatten one hash-bound storage claim at the application facade."""
    request = claim.selection_reason
    if not isinstance(request, dict):
        raise experiment_process_error("holdout_claim_request_drift")
    evidence_hash = request.get("expected_selection_evidence_hash")
    expected_revision = request.get("expected_experiment_revision")
    if (
        not isinstance(evidence_hash, str)
        or type(expected_revision) is not int
        or expected_revision + 1 != experiment_revision
    ):
        raise experiment_process_error("holdout_claim_request_drift")
    return PersistedHoldoutClaim(
        claim_id=claim.claim_id,
        experiment_id=str(claim.fold_key.experiment_id),
        candidate_id=str(claim.fold_key.candidate_id),
        fold_id=str(claim.fold_key.fold_id),
        logical_run_id=claim.logical_run_id,
        reproduction_fingerprint=str(claim.reproduction_fingerprint),
        claim_payload_hash=str(claim.claim_payload_hash),
        selection_evidence_hash=evidence_hash,
        resolved_spec_hash=str(claim.resolved_spec_hash),
        parameters_hash=str(claim.parameters_hash),
        snapshot_id=str(claim.snapshot_id),
        window_start=claim.window.start.isoformat(),
        window_end=claim.window.end.isoformat(),
        experiment_revision=experiment_revision,
        event_id=event_id,
        claimed_at=claim.claimed_at,
    )


def persisted_holdout_history(
    claim: StorageHoldoutClaim | None,
    events: Iterable[StorageStatusEvent],
) -> PersistedHoldoutClaim | None:
    """Rehydrate a claim only when its canonical stage event is unique."""
    if claim is None:
        return None
    request = claim.selection_reason
    revision = (
        request.get("expected_experiment_revision")
        if isinstance(request, dict)
        else None
    )
    expected_detail = {
        "schema_version": 1,
        "claim_id": claim.claim_id,
        "claim_payload_hash": str(claim.claim_payload_hash),
        "candidate_id": str(claim.fold_key.candidate_id),
        "fold_id": str(claim.fold_key.fold_id),
        "logical_run_id": claim.logical_run_id,
        "reproduction_fingerprint": str(claim.reproduction_fingerprint),
        "operator_confirmation": claim.operator_confirmation,
        "selection_request": request,
    }
    matches = tuple(
        event
        for event in events
        if type(revision) is int
        and event.subject_revision == revision + 1
        and str(event.experiment_id) == str(claim.fold_key.experiment_id)
        and event.candidate_id is None
        and event.fold_id is None
        and event.attempt_id is None
        and str(event.subject_type) == "experiment"
        and str(event.previous_status) == "running"
        and str(event.status) == "running"
        and str(event.desired_state) == "run"
        and str(event.stage) == "holdout"
        and event.failure_code is None
        and event.reason_code == "holdout_candidate_claimed"
        and without_validated_mutation_fence(event.detail) == expected_detail
        and event.occurred_at == claim.claimed_at
    )
    if len(matches) != 1:
        raise experiment_process_error("holdout_claim_event_drift")
    return persisted_holdout_claim(
        claim,
        experiment_revision=matches[0].subject_revision,
        event_id=matches[0].event_id,
    )
