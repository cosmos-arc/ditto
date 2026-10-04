"""Serialized in-process authority over the latest durable scheduler fence."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from threading import RLock
from typing import Protocol, TypeVar, cast
from uuid import uuid4

from ditto_analysis.errors import (
    AnalysisError,
    ExperimentConflictError,
    ExperimentIntegrityError,
    ExperimentLeaseLostError,
    ExperimentSpecError,
)
from ditto_analysis.experiments import (
    AttemptId,
    ExperimentId,
    LeaseFence,
    SchedulerLease,
    SchedulerSlot,
)

from ditto_application.exceptions import AppProcessError
from ditto_application.processes.experiments.scheduler_store import (
    ExperimentExecutionControlChanged,
    ExperimentSchedulerStoreProtocol,
    ResearchExecutionDirective,
)

__all__ = [
    "LeaseAuthority",
    "LeaseOperation",
    "ResearchExecutionControl",
    "require_utc_event_time",
    "run_unfenced_scheduler_operation",
]

_ResultT = TypeVar("_ResultT")
type LeaseOperation[ResultT] = Callable[[LeaseFence, int], ResultT]
_MICROSECONDS_PER_SECOND = 1_000_000
_SECONDS_PER_DAY = 86_400
_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
# Store rejections that mean "the slot serves other work right now"; a claim
# rejected for these reasons is ordinary busyness, not an authority failure.
_BUSY_CLAIM_REASONS = frozenset(
    {
        "scheduler_reclaim_required",
        "scheduler_experiment_not_eligible",
        "scheduler_claim_intent_mismatch",
    }
)


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _scheduler_error(code: str, reason: str, **details: object) -> AppProcessError:
    return AppProcessError(
        "experiment scheduler authority is unavailable",
        details={"code": code, "reason": reason, **details},
    )


def _epoch_us(value: datetime) -> int:
    raw = cast("object", value)
    if (
        type(raw) is not datetime
        or value.tzinfo is None
        or value.utcoffset() != timedelta(0)
    ):
        raise _scheduler_error("SPEC_INVALID", "occurred_at_must_be_utc")
    delta = value - _EPOCH
    return (
        delta.days * _SECONDS_PER_DAY + delta.seconds
    ) * _MICROSECONDS_PER_SECOND + delta.microseconds


def require_utc_event_time(value: datetime) -> None:
    """Validate an audit timestamp independently of the ownership clock."""
    _epoch_us(value)


def run_unfenced_scheduler_operation[ResultT](
    operation: Callable[[], ResultT],
) -> ResultT:
    """Normalize an operator CAS that intentionally does not need lease ownership."""
    try:
        return operation()
    except AppProcessError:
        raise
    except ExperimentLeaseLostError as exc:
        reason = str(exc.details.get("reason_code", "scheduler_lease_lost"))
        raise _scheduler_error("LEASE_LOST", reason) from exc
    except ExperimentConflictError as exc:
        code = str(exc.details.get("code", "CONFLICT"))
        reason = str(exc.details.get("reason_code", "operator_request_rejected"))
        details = {
            key: value
            for key, value in exc.details.items()
            if key not in {"code", "reason_code"}
        }
        raise _scheduler_error(code, reason, **details) from exc
    except ExperimentSpecError as exc:
        reason = str(exc.details.get("reason_code", "scheduler_spec_invalid"))
        raise _scheduler_error("SPEC_INVALID", reason) from exc
    except ExperimentIntegrityError as exc:
        reason = str(
            exc.details.get("reason_code", "scheduler_persistence_integrity_failed")
        )
        raise _scheduler_error("EXPERIMENT_INTEGRITY_FAILED", reason) from exc
    except AnalysisError as exc:
        code = str(exc.details.get("code", "SYSTEM_ERROR"))
        reason = str(exc.details.get("reason_code", "scheduler_control_write_failed"))
        raise _scheduler_error(code, reason) from exc


class LeaseAuthority:
    """
    Own one durable slot claim and serialize all fenced scheduler operations.

    The slot CAS is the single-writer authority (#448: no renew, expiry, or
    handoff; a stale owner's writes fail closed against the latest revision).
    """

    def __init__(
        self,
        store: ExperimentSchedulerStoreProtocol,
        *,
        owner_token: str,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        raw_owner = cast("object", owner_token)
        if (
            type(raw_owner) is not str
            or not owner_token.strip()
            or owner_token != owner_token.strip()
        ):
            raise _scheduler_error("SPEC_INVALID", "owner_token_invalid")
        self._store = store
        self._owner_token = f"{owner_token}:{uuid4().hex}"
        self._clock = clock or _utc_now
        self._lock = RLock()
        self._lease: SchedulerLease | None = None
        self._lost_reason: str | None = None

    @property
    def has_lease(self) -> bool:
        """Return whether this coordinator currently has a usable lease object."""
        with self._lock:
            return self._lease is not None and self._lost_reason is None

    @property
    def is_lost(self) -> bool:
        """Return whether a fence or integrity failure permanently invalidated it."""
        with self._lock:
            return self._lost_reason is not None

    def ensure_usable(self) -> None:
        """Fail before reads or writes once this coordinator lost authority."""
        with self._lock:
            self._raise_if_lost()

    def require_current_lease(self) -> SchedulerLease:
        """Return the current claim for read-only fence inspection."""
        with self._lock:
            return self._require_live_lease()

    def fail_closed(self, error: Exception) -> AppProcessError:
        """Permanently invalidate this authority after an unowned integrity read."""
        with self._lock:
            self._invalidate(type(error).__name__)
            return self._normalized_error(error)

    def acquire(
        self,
        experiment_id: ExperimentId,
        *,
        expected_revision: int,
    ) -> bool:
        """Try to claim the singleton slot by revisioned CAS."""
        with self._lock:
            self._raise_if_lost()
            if self._lease is not None:
                if self._lease.experiment_id != experiment_id:
                    raise _scheduler_error(
                        "LEASE_LOST", "authority_already_bound_to_other_experiment"
                    )
                return True
            lease = self._claim_from_store(experiment_id, expected_revision)
            if lease is None:
                return False
            self._lease = lease
            return True

    def _claim_from_store(
        self,
        experiment_id: ExperimentId,
        expected_revision: int,
    ) -> SchedulerLease | None:
        """Claim once, mapping retryable rejections to a lost race."""
        try:
            return self._store.try_claim_lease(
                experiment_id,
                self._owner_token,
                expected_revision=expected_revision,
                now_epoch_us=self._audit_epoch_us(),
            )
        except ExperimentLeaseLostError as exc:
            if exc.details.get("reason_code") == "scheduler_lease_stale_revision":
                return None
            self._invalidate(type(exc).__name__)
            raise self._normalized_error(exc) from exc
        except ExperimentSpecError as exc:
            if self._is_busy_claim_rejection(exc):
                return None
            self._invalidate(type(exc).__name__)
            raise self._normalized_error(exc) from exc
        except AppProcessError:
            if self._lost_reason is None:
                self._invalidate("application_contract_failure")
            raise
        except Exception as exc:
            self._invalidate(type(exc).__name__)
            raise self._normalized_error(exc) from exc

    @staticmethod
    def _is_busy_claim_rejection(exc: ExperimentSpecError) -> bool:
        """
        Whether the store rejected the claim because the slot is busy.

        The slot legitimately serving another occupant is ordinary busyness,
        not an authority failure: a process-lifetime control coordinator must
        survive an ordinary "other experiment is running" rejection.
        """
        return exc.details.get("reason_code") in _BUSY_CLAIM_REASONS

    def execute(
        self,
        operation: Callable[[SchedulerLease, Callable[[], int]], _ResultT],
    ) -> _ResultT:
        """Run one complete read/write section under the latest durable fence."""
        with self._lock:
            try:
                lease = self._require_live_lease()
                return operation(lease, self._fenced_now_epoch_us)
            except ExperimentExecutionControlChanged:
                raise
            except AppProcessError:
                if self._lost_reason is None:
                    self._invalidate("application_contract_failure")
                raise
            except Exception as exc:
                self._invalidate(type(exc).__name__)
                raise self._normalized_error(exc) from exc

    def execute_operator(
        self,
        operation: Callable[[SchedulerLease, Callable[[], int]], _ResultT],
    ) -> _ResultT:
        """Run a fenced operator CAS without poisoning authority on 4xx rejection."""
        with self._lock:
            try:
                lease = self._require_live_lease()
                return operation(lease, self._fenced_now_epoch_us)
            except ExperimentExecutionControlChanged:
                raise
            except AppProcessError as exc:
                if exc.details.get("code") in {
                    "LEASE_LOST",
                    "EXPERIMENT_INTEGRITY_FAILED",
                }:
                    self._invalidate("operator_authority_failure")
                raise
            except (ExperimentLeaseLostError, ExperimentIntegrityError) as exc:
                self._invalidate(type(exc).__name__)
                raise self._normalized_error(exc) from exc
            except (ExperimentConflictError, ExperimentSpecError) as exc:
                code = (
                    str(exc.details.get("code", "CONFLICT"))
                    if isinstance(exc, ExperimentConflictError)
                    else "SPEC_INVALID"
                )
                reason = str(
                    exc.details.get("reason_code", "operator_request_rejected")
                )
                details = {
                    key: value
                    for key, value in exc.details.items()
                    if key not in {"code", "reason_code"}
                }
                raise _scheduler_error(code, reason, **details) from exc
            except Exception as exc:
                self._invalidate(type(exc).__name__)
                raise self._normalized_error(exc) from exc

    def execute_operator_under_transient_lease(
        self,
        experiment_id: ExperimentId,
        *,
        expected_revision: int,
        operation: Callable[[SchedulerLease, Callable[[], int]], _ResultT],
    ) -> _ResultT:
        """
        Acquire, execute, and forget one transient claim as one authority section.

        The outer reentrant lock makes the ownership decision atomic with lease
        acquisition and operator execution. A lease already held by this
        authority belongs to the scheduler lifecycle and is preserved. Only a
        lease acquired by this call is forgotten afterwards: the durable slot
        row stays occupied until the next claimant revision-overwrites it, so
        no concurrent stale writer can slip in behind the operator.
        """
        with self._lock:
            acquired_transient_lease = self._lease is None
            acquired = self.acquire(
                experiment_id,
                expected_revision=expected_revision,
            )
            if not acquired:
                raise AppProcessError(
                    "experiment scheduler operation failed",
                    details={
                        "code": "LEASE_LOST",
                        "reason": "scheduler_slot_busy",
                    },
                )
            try:
                return self.execute_operator(operation)
            finally:
                if acquired_transient_lease:
                    self._lease = None

    def execute_recoverable_publication(
        self,
        operation: LeaseOperation[_ResultT],
    ) -> _ResultT:
        """
        Synchronously publish recoverable evidence under the current fence.

        The callback receives the current fence and an authority-clock
        timestamp, and runs before the outer authority section can be released.
        It must complete the publication synchronously and must not recursively
        claim this authority. Ordinary publication failures leave the authority
        usable so the worker can durably fail its attempt. Authority,
        integrity, replay-conflict, and unknown interruption outcomes fail
        closed.
        """
        with self._lock:
            try:
                now_epoch_us = _epoch_us(self._clock())
                current = self._require_live_lease()
            except AppProcessError:
                if self._lost_reason is None:
                    self._invalidate("application_contract_failure")
                raise
            except Exception as exc:
                self._invalidate(type(exc).__name__)
                raise self._normalized_error(exc) from exc
            return self._execute_recoverable_publication(
                operation,
                current.fence,
                now_epoch_us,
            )

    def release(self) -> SchedulerSlot:
        """Release one terminal occupant and keep this authority reusable."""
        with self._lock:
            try:
                lease = self._require_live_lease()
                released = self._store.release_lease(lease)
                if released.experiment_id is not None:
                    raise _scheduler_error(
                        "EXPERIMENT_INTEGRITY_FAILED",
                        "scheduler_release_returned_occupied_slot",
                    )
            except AppProcessError:
                if self._lost_reason is None:
                    self._invalidate("application_contract_failure")
                raise
            except Exception as exc:
                self._invalidate(type(exc).__name__)
                raise self._normalized_error(exc) from exc
            self._lease = None
            return released

    def forget_lease(self) -> None:
        """
        Forget one operator-gate claim without touching the durable slot.

        Used when a tick parks the experiment at an operator gate: the durable
        slot row stays occupied by the (now idle) owner, and the next claimant
        — the next tick or an operator route — reclaims it in place by CAS.
        """
        with self._lock:
            self._raise_if_lost()
            self._lease = None

    def _audit_epoch_us(self) -> int:
        return _epoch_us(self._clock())

    def _fenced_now_epoch_us(self) -> int:
        self._require_live_lease()
        return _epoch_us(self._clock())

    def _execute_recoverable_publication(
        self,
        operation: LeaseOperation[_ResultT],
        lease_fence: LeaseFence,
        now_epoch_us: int,
    ) -> _ResultT:
        """Classify only the synchronous artifact publication outcome."""
        try:
            return operation(lease_fence, now_epoch_us)
        except AppProcessError as exc:
            if exc.details.get("code") in {
                "LEASE_LOST",
                "EXPERIMENT_INTEGRITY_FAILED",
            }:
                self._invalidate("artifact_publication_authority_failure")
            raise
        except ExperimentLeaseLostError as exc:
            self._invalidate(type(exc).__name__)
            raise self._normalized_error(exc) from exc
        except ExperimentIntegrityError as exc:
            self._invalidate(type(exc).__name__)
            raise self._normalized_error(exc) from exc
        except ExperimentConflictError as exc:
            self._invalidate(type(exc).__name__)
            raise _scheduler_error(
                "EXPERIMENT_INTEGRITY_FAILED",
                "artifact_publication_conflict",
                conflict_reason=str(
                    exc.details.get("reason_code", "artifact_replay_drift")
                ),
            ) from exc
        except Exception:
            raise
        except BaseException:
            self._invalidate("artifact_publication_interrupted")
            raise

    def _require_live_lease(self) -> SchedulerLease:
        self._raise_if_lost()
        lease = self._lease
        if lease is None:
            raise _scheduler_error("LEASE_LOST", "scheduler_lease_not_acquired")
        return lease

    def _raise_if_lost(self) -> None:
        if self._lost_reason is not None:
            raise _scheduler_error(
                "LEASE_LOST",
                "scheduler_authority_invalidated",
                lost_reason=self._lost_reason,
            )

    def _invalidate(self, reason: str) -> None:
        self._lease = None
        self._lost_reason = reason

    @staticmethod
    def _normalized_error(error: Exception) -> AppProcessError:
        if isinstance(error, ExperimentLeaseLostError):
            return _scheduler_error("LEASE_LOST", "scheduler_lease_lost")
        if isinstance(error, ExperimentIntegrityError):
            return _scheduler_error(
                "EXPERIMENT_INTEGRITY_FAILED",
                "scheduler_persistence_integrity_failed",
            )
        if isinstance(error, ExperimentSpecError):
            return _scheduler_error(
                "SPEC_INVALID",
                str(error.details.get("reason_code", "scheduler_spec_invalid")),
            )
        if isinstance(error, AnalysisError):
            return _scheduler_error(
                "SYSTEM_ERROR",
                "scheduler_persistence_operation_failed",
                error_type=type(error).__name__,
            )
        return _scheduler_error(
            "SYSTEM_ERROR",
            "scheduler_operation_failed",
            error_type=type(error).__name__,
        )


class _ExecutionControlCoordinator(Protocol):
    def poll_execution_directive(
        self,
        attempt_id: AttemptId,
        *,
        occurred_at: datetime,
    ) -> ResearchExecutionDirective: ...


class ResearchExecutionControl:
    """Lease-aware durable stop callback polled by BacktestService."""

    def __init__(
        self,
        *,
        coordinator: _ExecutionControlCoordinator,
        attempt_id: AttemptId,
        clock: Callable[[], datetime],
    ) -> None:
        self._coordinator = coordinator
        self._attempt_id = attempt_id
        self._clock = clock
        self._lock = RLock()
        self._failure: AppProcessError | None = None
        self._directive = ResearchExecutionDirective.RUN

    @property
    def failure(self) -> AppProcessError | None:
        """Return the first durable authority failure, if one occurred."""
        with self._lock:
            return self._failure

    @property
    def directive(self) -> ResearchExecutionDirective:
        """Return the latest durable execution directive observed."""
        with self._lock:
            return self._directive

    def should_stop(self) -> bool:
        """Read server truth and fail closed on authority errors."""
        with self._lock:
            if self._failure is not None:
                return True
            try:
                occurred_at = self._clock()
                self._directive = self._coordinator.poll_execution_directive(
                    self._attempt_id,
                    occurred_at=occurred_at,
                )
            except AppProcessError as error:
                self._failure = error
                return True
            except Exception as error:  # pragma: no cover - defensive port boundary
                self._failure = AppProcessError(
                    "research execution control poll failed",
                    details={
                        "code": "SYSTEM_ERROR",
                        "reason": "execution_control_poll_failed",
                        "error_type": type(error).__name__,
                    },
                )
                return True
            return self._directive is not ResearchExecutionDirective.RUN
