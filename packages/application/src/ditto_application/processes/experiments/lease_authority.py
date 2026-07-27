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
    "ResearchExecutionControl",
    "require_utc_event_time",
    "run_unfenced_scheduler_operation",
]

_ResultT = TypeVar("_ResultT")
_MICROSECONDS_PER_SECOND = 1_000_000
_SECONDS_PER_DAY = 86_400
_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _scheduler_error(code: str, reason: str, **details: object) -> AppProcessError:
    return AppProcessError(
        "experiment scheduler authority is unavailable",
        details={"code": code, "reason": reason, **details},
    )


def _transient_release_failure_note(error: BaseException) -> str:
    note = (
        "transient scheduler lease release also failed: "
        + f"{type(error).__name__}: {error}"
    )
    if isinstance(error, AppProcessError):
        return (
            f"{note}; code={error.details.get('code')}; "
            + f"reason={error.details.get('reason')}"
        )
    return note


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
    """Validate an audit timestamp without using it as the lease clock."""
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


def _duration_us(value: timedelta) -> int:
    raw = cast("object", value)
    if type(raw) is not timedelta:
        raise _scheduler_error("SPEC_INVALID", "lease_duration_must_be_timedelta")
    duration = (
        value.days * _SECONDS_PER_DAY + value.seconds
    ) * _MICROSECONDS_PER_SECOND + value.microseconds
    if duration <= 0:
        raise _scheduler_error("SPEC_INVALID", "lease_duration_must_be_positive")
    return duration


class LeaseAuthority:
    """Own one latest lease and serialize all fenced scheduler operations."""

    def __init__(
        self,
        store: ExperimentSchedulerStoreProtocol,
        *,
        owner_token: str,
        lease_duration: timedelta,
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
        self._lease_duration_us = _duration_us(lease_duration)
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

    def now_epoch_us(self) -> int:
        """Read the authoritative lease clock independently of audit timestamps."""
        with self._lock:
            self._raise_if_lost()
            try:
                return _epoch_us(self._clock())
            except AppProcessError:
                self._invalidate("invalid_authoritative_clock")
                raise
            except Exception as exc:
                self._invalidate(type(exc).__name__)
                raise self._normalized_error(exc) from exc

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
        """Try to bind the singleton slot without replacing an active authority."""
        with self._lock:
            self._raise_if_lost()
            now_epoch_us = self.now_epoch_us()
            if self._lease is not None:
                if self._lease.experiment_id != experiment_id:
                    raise _scheduler_error(
                        "LEASE_LOST", "authority_already_bound_to_other_experiment"
                    )
                return True
            try:
                lease = self._store.try_claim_lease(
                    experiment_id,
                    self._owner_token,
                    expected_revision=expected_revision,
                    now_epoch_us=now_epoch_us,
                    lease_until_epoch_us=now_epoch_us + self._lease_duration_us,
                )
            except ExperimentLeaseLostError as exc:
                if exc.details.get("reason_code") == "scheduler_lease_stale_revision":
                    return False
                self._invalidate(type(exc).__name__)
                raise self._normalized_error(exc) from exc
            except AppProcessError:
                if self._lost_reason is None:
                    self._invalidate("application_contract_failure")
                raise
            except Exception as exc:
                self._invalidate(type(exc).__name__)
                raise self._normalized_error(exc) from exc
            if lease is None:
                return False
            self._lease = lease
            return True

    def execute(
        self,
        operation: Callable[[SchedulerLease, Callable[[], int]], _ResultT],
    ) -> _ResultT:
        """Run one complete read/write section under the latest unexpired fence."""
        with self._lock:
            try:
                lease = self._require_live_lease(_epoch_us(self._clock()))
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
                lease = self._require_live_lease(_epoch_us(self._clock()))
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
        Acquire, execute, and conditionally release as one authority section.

        The outer reentrant lock makes the ownership decision atomic with lease
        acquisition, operator execution, and cleanup. A lease already held by
        this authority belongs to the scheduler lifecycle and is preserved.
        Only a lease acquired by this call is released.
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
                result = self.execute_operator(operation)
            except BaseException as error:
                if (
                    acquired_transient_lease
                    and self._lease is not None
                    and self._lost_reason is None
                ):
                    try:
                        self._release_transient_fail_closed()
                    except BaseException as release_error:
                        error.add_note(_transient_release_failure_note(release_error))
                raise
            if acquired_transient_lease:
                self._release_transient_fail_closed()
            return result

    def renew(self) -> SchedulerLease:
        """Renew with the current fence and replace it before any later write."""
        with self._lock:
            try:
                now_epoch_us = _epoch_us(self._clock())
                lease = self._require_live_lease(now_epoch_us)
                renewed = self._store.renew_lease(
                    lease,
                    now_epoch_us=now_epoch_us,
                    new_lease_until_epoch_us=(now_epoch_us + self._lease_duration_us),
                )
            except AppProcessError:
                if self._lost_reason is None:
                    self._invalidate("application_contract_failure")
                raise
            except Exception as exc:
                self._invalidate(type(exc).__name__)
                raise self._normalized_error(exc) from exc
            self._lease = renewed
            return renewed

    def release(self) -> SchedulerSlot:
        """Release one terminal occupant and keep this authority reusable."""
        with self._lock:
            try:
                now_epoch_us = _epoch_us(self._clock())
                lease = self._require_live_lease(now_epoch_us)
                released = self._store.release_lease(
                    lease,
                    now_epoch_us=now_epoch_us,
                )
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

    def _fenced_now_epoch_us(self) -> int:
        now_epoch_us = _epoch_us(self._clock())
        self._require_live_lease(now_epoch_us)
        return now_epoch_us

    def _release_transient_fail_closed(self) -> SchedulerSlot:
        try:
            return self.release()
        except BaseException as error:
            if self._lost_reason is None:
                self._invalidate(type(error).__name__)
            raise

    def _require_live_lease(self, now_epoch_us: int) -> SchedulerLease:
        self._raise_if_lost()
        lease = self._lease
        if lease is None:
            raise _scheduler_error("LEASE_LOST", "scheduler_lease_not_acquired")
        if lease.lease_until_epoch_us <= now_epoch_us:
            self._invalidate("scheduler_lease_expired")
            raise _scheduler_error("LEASE_LOST", "scheduler_lease_expired")
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
    def renew_lease(self, *, occurred_at: datetime) -> SchedulerLease: ...

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
        self._failure: AppProcessError | None = None
        self._directive = ResearchExecutionDirective.RUN

    @property
    def failure(self) -> AppProcessError | None:
        """Return the first durable authority failure, if one occurred."""
        return self._failure

    @property
    def directive(self) -> ResearchExecutionDirective:
        """Return the latest durable execution directive observed."""
        return self._directive

    def should_stop(self) -> bool:
        """Renew, read server truth, and fail closed on authority errors."""
        if self._failure is not None:
            return True
        try:
            occurred_at = self._clock()
            self._coordinator.renew_lease(occurred_at=occurred_at)
            self._directive = self._coordinator.poll_execution_directive(
                self._attempt_id,
                occurred_at=occurred_at,
            )
        except AppProcessError as error:
            self._failure = error
            return True
        except Exception as error:  # pragma: no cover - defensive port boundary
            self._failure = AppProcessError(
                "research execution lease renewal failed",
                details={
                    "code": "SYSTEM_ERROR",
                    "reason": "lease_renewal_failed",
                    "error_type": type(error).__name__,
                },
            )
            return True
        return self._directive is not ResearchExecutionDirective.RUN
