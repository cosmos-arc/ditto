"""Pure snapshot invariants for the durable experiment coordinator."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol, cast

from ditto_application.exceptions import AppProcessError
from ditto_application.processes.experiments.scheduler_store import (
    ExperimentSchedulerSnapshot,
)


class _EnumValue(Protocol):
    @property
    def value(self) -> str: ...


class _AttemptSpec(Protocol):
    @property
    def attempt_id(self) -> object: ...

    @property
    def fold_key(self) -> object: ...


class _AttemptProjection(Protocol):
    @property
    def attempt_id(self) -> object: ...

    @property
    def status(self) -> _EnumValue: ...

    @property
    def backtest_run_id(self) -> object | None: ...

    @property
    def failure_code(self) -> object | None: ...


class _AttemptFact(Protocol):
    @property
    def spec(self) -> _AttemptSpec: ...

    @property
    def projection(self) -> _AttemptProjection: ...


class _FoldSpec(Protocol):
    @property
    def key(self) -> object: ...

    @property
    def fold_role(self) -> object: ...


class _FoldProjection(Protocol):
    @property
    def key(self) -> object: ...

    @property
    def status(self) -> object: ...

    @property
    def claim_owner_token(self) -> str | None: ...


class _FoldFact(Protocol):
    @property
    def spec(self) -> _FoldSpec: ...

    @property
    def projection(self) -> _FoldProjection: ...


class _DispatchFact(Protocol):
    @property
    def stage(self) -> object: ...

    @property
    def fold(self) -> _FoldFact: ...

    @property
    def attempt(self) -> _AttemptFact: ...


class _LeaseFact(Protocol):
    @property
    def owner_token(self) -> str: ...


@dataclass(frozen=True, slots=True)
class SnapshotVocabulary:
    """Exact analysis-owned enum members supplied by the allowed coordinator."""

    live_statuses: frozenset[object]
    terminal_work_statuses: frozenset[object]
    hard_failure_codes: frozenset[object]
    first_run_failure_codes: frozenset[object]
    replayable_terminal_statuses: frozenset[object]
    failed_status: object
    queued_status: object
    running_status: object
    cancelled_status: object
    candidate_failed_code: object
    fail_fast_policy: object
    stage_role: Mapping[object, object]
    role_order: Mapping[object, int]
    stage_role_ceiling: Mapping[object, int]
    prior_fold_roles: Mapping[object, tuple[object, ...]]


def erase_mapping_keys[KeyT, ValueT](
    mapping: Mapping[KeyT, ValueT],
) -> Mapping[object, ValueT]:
    """Erase only key variance after coordinator-owned enum construction."""
    return cast("Mapping[object, ValueT]", mapping)


def scheduler_error(code: str, reason: str, **details: object) -> AppProcessError:
    """Build the coordinator's stable typed application error."""
    return AppProcessError(
        "experiment scheduler operation failed",
        details={"code": code, "reason": reason, **details},
    )


def require_exact_persisted_dispatch(
    snapshot: ExperimentSchedulerSnapshot,
    dispatch: object,
    attempt: object,
    fold: object,
    lease: object,
    vocabulary: SnapshotVocabulary,
) -> None:
    """Validate a queued dispatch against its exact persisted owned claim."""
    dispatch_fact = cast("_DispatchFact", dispatch)
    attempt_fact = cast("_AttemptFact", attempt)
    fold_fact = cast("_FoldFact", fold)
    lease_fact = cast("_LeaseFact", lease)
    expected_role = vocabulary.stage_role.get(dispatch_fact.stage)
    if (
        snapshot.projection.record.stage is not dispatch_fact.stage
        or expected_role is None
        or dispatch_fact.fold.spec.fold_role is not expected_role
        or fold_fact.spec.fold_role is not expected_role
    ):
        raise scheduler_error(
            "EXPERIMENT_INTEGRITY_FAILED",
            "dispatch_stage_role_mismatch",
        )
    if (
        dispatch_fact.attempt.spec != attempt_fact.spec
        or dispatch_fact.attempt.projection.attempt_id
        != dispatch_fact.attempt.spec.attempt_id
        or dispatch_fact.attempt.projection.status is not vocabulary.queued_status
        or dispatch_fact.attempt.projection.backtest_run_id is not None
    ):
        raise scheduler_error(
            "EXPERIMENT_INTEGRITY_FAILED",
            "dispatch_attempt_identity_drift",
        )
    if (
        dispatch_fact.fold.spec != fold_fact.spec
        or dispatch_fact.fold.projection.key != dispatch_fact.fold.spec.key
        or dispatch_fact.fold.projection.status is not vocabulary.running_status
        or dispatch_fact.fold.projection.claim_owner_token != lease_fact.owner_token
        or dispatch_fact.attempt.spec.fold_key != dispatch_fact.fold.spec.key
    ):
        raise scheduler_error(
            "EXPERIMENT_INTEGRITY_FAILED",
            "dispatch_fold_identity_drift",
        )


def require_exact_terminal_replay(
    dispatch: object,
    attempt: object,
    fold: object,
    expected_run_id: object,
    vocabulary: SnapshotVocabulary,
) -> None:
    """Validate an immutable late delivery without requiring a released claim."""
    dispatch_fact = cast("_DispatchFact", dispatch)
    attempt_fact = cast("_AttemptFact", attempt)
    fold_fact = cast("_FoldFact", fold)
    expected_role = vocabulary.stage_role.get(dispatch_fact.stage)
    if (
        expected_role is None
        or dispatch_fact.fold.spec.fold_role is not expected_role
        or fold_fact.spec.fold_role is not expected_role
    ):
        raise scheduler_error(
            "EXPERIMENT_INTEGRITY_FAILED",
            "dispatch_stage_role_mismatch",
        )
    if (
        dispatch_fact.attempt.spec != attempt_fact.spec
        or dispatch_fact.attempt.projection.attempt_id
        != dispatch_fact.attempt.spec.attempt_id
        or dispatch_fact.attempt.projection.status is not vocabulary.queued_status
        or dispatch_fact.attempt.projection.backtest_run_id is not None
    ):
        raise scheduler_error(
            "EXPERIMENT_INTEGRITY_FAILED",
            "dispatch_attempt_identity_drift",
        )
    if (
        dispatch_fact.fold.spec != fold_fact.spec
        or dispatch_fact.fold.projection.key != dispatch_fact.fold.spec.key
        or dispatch_fact.fold.projection.status is not vocabulary.running_status
        or dispatch_fact.fold.projection.claim_owner_token is None
        or dispatch_fact.attempt.spec.fold_key != dispatch_fact.fold.spec.key
    ):
        raise scheduler_error(
            "EXPERIMENT_INTEGRITY_FAILED",
            "dispatch_fold_identity_drift",
        )
    status = attempt_fact.projection.status
    if (
        status not in vocabulary.replayable_terminal_statuses
        or fold_fact.projection.status is not status
        or fold_fact.projection.claim_owner_token is not None
        or attempt_fact.projection.backtest_run_id != expected_run_id
        or (
            status is not vocabulary.failed_status
            and attempt_fact.projection.failure_code is not None
        )
        or (
            status is vocabulary.failed_status
            and attempt_fact.projection.failure_code
            not in vocabulary.first_run_failure_codes
        )
    ):
        raise scheduler_error(
            "EXPERIMENT_INTEGRITY_FAILED",
            "attempt_terminal_replay_invalid",
        )


def candidate_failure_ids(
    snapshot: ExperimentSchedulerSnapshot,
    vocabulary: SnapshotVocabulary,
) -> frozenset[object]:
    """Return exact candidate identities with a durable candidate failure."""
    return frozenset(
        attempt.spec.fold_key.candidate_id
        for attempt in snapshot.attempts
        if attempt.projection.status is vocabulary.failed_status
        and attempt.projection.failure_code is vocabulary.candidate_failed_code
    )


def hard_failure_count(
    snapshot: ExperimentSchedulerSnapshot,
    vocabulary: SnapshotVocabulary,
) -> int:
    """Count persisted hard failures without inferring in-memory progress."""
    return sum(
        1
        for attempt in snapshot.attempts
        if attempt.projection.status is vocabulary.failed_status
        and attempt.projection.failure_code in vocabulary.hard_failure_codes
    )


def must_stop_after_failure(
    snapshot: ExperimentSchedulerSnapshot,
    vocabulary: SnapshotVocabulary,
) -> bool:
    """Apply the frozen failure policy to durable attempt outcomes."""
    if hard_failure_count(snapshot, vocabulary) > 0:
        return True
    failed_candidates = candidate_failure_ids(snapshot, vocabulary)
    if not failed_candidates:
        return False
    if snapshot.launch_spec.failure_policy is vocabulary.fail_fast_policy:
        return True
    return failed_candidates == frozenset(
        candidate.candidate_id for candidate in snapshot.launch_spec.candidates
    )


def validate_live_work_stage(
    snapshot: ExperimentSchedulerSnapshot,
    vocabulary: SnapshotVocabulary,
) -> None:
    """Reject live attempts whose fold sits outside the current stage role."""
    current_role = vocabulary.stage_role.get(snapshot.projection.record.stage)
    live_attempt_keys = {
        attempt.spec.fold_key
        for attempt in snapshot.attempts
        if attempt.projection.status in vocabulary.live_statuses
    }
    live_fold_keys = {
        fold.spec.key
        for fold in snapshot.folds
        if fold.projection.status in vocabulary.live_statuses
        and fold.spec.key in live_attempt_keys
    }
    if live_fold_keys and (
        current_role is None
        or any(
            fold.spec.key in live_fold_keys and fold.spec.fold_role is not current_role
            for fold in snapshot.folds
        )
    ):
        raise scheduler_error(
            "EXPERIMENT_INTEGRITY_FAILED",
            "live_work_outside_current_stage",
        )


def validate_no_future_stage_outcomes(
    snapshot: ExperimentSchedulerSnapshot,
    vocabulary: SnapshotVocabulary,
) -> None:
    """Allow future folds only when queued or candidate-isolation cancelled."""
    role_ceiling = vocabulary.stage_role_ceiling.get(
        snapshot.projection.record.stage,
        -1,
    )
    folds_by_key = {fold.spec.key: fold for fold in snapshot.folds}
    for attempt in snapshot.attempts:
        fold = folds_by_key[attempt.spec.fold_key]
        if vocabulary.role_order[fold.spec.fold_role] > role_ceiling:
            raise scheduler_error(
                "EXPERIMENT_INTEGRITY_FAILED",
                "future_stage_attempt_detected",
            )
    failed_candidates = candidate_failure_ids(snapshot, vocabulary)
    for fold in snapshot.folds:
        if vocabulary.role_order[fold.spec.fold_role] <= role_ceiling:
            continue
        if fold.projection.status is vocabulary.queued_status:
            continue
        if (
            fold.projection.status is vocabulary.cancelled_status
            and fold.spec.key.candidate_id in failed_candidates
        ):
            continue
        raise scheduler_error(
            "EXPERIMENT_INTEGRITY_FAILED",
            "future_stage_fold_outcome_detected",
        )


def validate_stage_frontier(
    snapshot: ExperimentSchedulerSnapshot,
    vocabulary: SnapshotVocabulary,
) -> None:
    """Require every prior fold role to be terminal before a persisted stage."""
    stage = snapshot.projection.record.stage
    prior_roles = vocabulary.prior_fold_roles.get(stage)
    if prior_roles is None:
        raise scheduler_error(
            "EXPERIMENT_INTEGRITY_FAILED",
            "stage_frontier_unknown",
            stage=stage.value,
        )
    for role in prior_roles:
        incomplete = next(
            (
                fold
                for fold in snapshot.folds
                if fold.spec.fold_role is role
                and fold.projection.status not in vocabulary.terminal_work_statuses
            ),
            None,
        )
        if incomplete is not None:
            raise scheduler_error(
                "EXPERIMENT_INTEGRITY_FAILED",
                "stage_frontier_incomplete",
                stage=stage.value,
                fold_role=cast("_EnumValue", role).value,
                fold_id=str(incomplete.spec.key.fold_id),
                fold_status=incomplete.projection.status.value,
            )


def requires_recovery(
    snapshot: ExperimentSchedulerSnapshot,
    lease_owner_token: str,
    vocabulary: SnapshotVocabulary,
) -> bool:
    """Detect a split or orphaned durable fold/attempt claim."""
    attempts_by_fold: dict[object, list[_AttemptFact]] = {
        fold.spec.key: [] for fold in snapshot.folds
    }
    for attempt in snapshot.attempts:
        attempts_by_fold[attempt.spec.fold_key].append(cast("_AttemptFact", attempt))
    for fold in snapshot.folds:
        live_attempts = tuple(
            attempt
            for attempt in attempts_by_fold[fold.spec.key]
            if attempt.projection.status in vocabulary.live_statuses
        )
        if fold.projection.status is vocabulary.running_status:
            if (
                fold.projection.claim_owner_token != lease_owner_token
                or len(live_attempts) != 1
            ):
                return True
        elif live_attempts:
            return True
    return False


def validate_worker_limit(snapshot: ExperimentSchedulerSnapshot) -> None:
    """Accept only the frozen bounded worker limits."""
    if snapshot.launch_spec.worker_count not in {2, 4}:
        raise scheduler_error("SPEC_INVALID", "worker_limit_must_be_two_or_four")


def validate_durable_worker_capacity(
    snapshot: ExperimentSchedulerSnapshot,
    vocabulary: SnapshotVocabulary,
) -> None:
    """Reject persisted live work that already exceeds the frozen limit."""
    live_attempt_count = sum(
        1
        for attempt in snapshot.attempts
        if attempt.projection.status in vocabulary.live_statuses
    )
    worker_limit = snapshot.launch_spec.worker_count
    if live_attempt_count > worker_limit:
        raise scheduler_error(
            "SPEC_INVALID",
            "durable_worker_capacity_exceeded",
            worker_limit=worker_limit,
            live_attempt_count=live_attempt_count,
        )
