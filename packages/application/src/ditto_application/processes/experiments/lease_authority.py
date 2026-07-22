"""Serialized in-process authority over the latest durable scheduler fence."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from threading import RLock
from typing import TypeVar, cast
from uuid import uuid4

from ditto_analysis.errors import (
    AnalysisError,
    ExperimentIntegrityError,
    ExperimentLeaseLostError,
)
from ditto_analysis.experiments import ExperimentId, SchedulerLease

from ditto_application.exceptions import AppProcessError
from ditto_application.processes.experiments.scheduler_store import (
    ExperimentSchedulerStoreProtocol,
)

__all__ = ["LeaseAuthority"]

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
            except AppProcessError:
                if self._lost_reason is None:
                    self._invalidate("application_contract_failure")
                raise
            except Exception as exc:
                self._invalidate(type(exc).__name__)
                raise self._normalized_error(exc) from exc

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

    def _fenced_now_epoch_us(self) -> int:
        now_epoch_us = _epoch_us(self._clock())
        self._require_live_lease(now_epoch_us)
        return now_epoch_us

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
