"""R3 control-only runtime wiring: best-effort notifier + placeholder factory.

The control routes need a production ``ExperimentControlNotifier`` and a
``FirstAttemptFactory`` to construct ``ExperimentExecutionCoordinator``. In the
R3 single-machine durable-tick model the notifier only logs (the worker already
polls durable ``desired_state``), and control operations never dispatch attempts
so the placeholder factory fails loudly if ever invoked.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Event, Lock
from typing import cast
from unittest.mock import MagicMock

import pytest
from ditto_analysis.experiments import (
    AttemptView,
    ExperimentId,
    FoldView,
    SchedulerLease,
    SchedulerSlot,
)
from ditto_application.exceptions import AppProcessError
from ditto_application.processes.experiments._control_runtime import (
    CONTROL_ONLY_FACTORY_CODE,
    CONTROL_ONLY_FACTORY_REASON,
    ControlOnlyFirstAttemptFactory,
    LoggingExperimentControlNotifier,
    RetryFoldControlRequest,
    retry_fold_under_transient_lease,
)
from ditto_application.processes.experiments._coordinator_contract import (
    ExperimentControlReceipt,
)
from ditto_application.processes.experiments._coordinator_recovery import (
    ExperimentRecoveryOrchestrator,
)
from ditto_application.processes.experiments.lease_authority import LeaseAuthority
from ditto_application.processes.experiments.scheduler_store import (
    ExperimentSchedulerStoreProtocol,
)

_NOW = datetime(2026, 7, 25, 0, 0, tzinfo=UTC)
_EXPERIMENT_ID = ExperimentId("experiment-control-runtime")
_RECEIPT = ExperimentControlReceipt(
    experiment_id=str(_EXPERIMENT_ID),
    status="running",
    desired_state="run",
    revision=1,
    occurred_at=_NOW,
)


class _ControlStore:
    """Thread-safe lease store exposing ownership and cleanup outcomes."""

    def __init__(self, *, release_error: BaseException | None = None) -> None:
        self.slot = SchedulerSlot("global", None, None, None, None, None, 0)
        self.release_calls = 0
        self.release_error = release_error
        self._lock = Lock()

    def get_scheduler_slot(self) -> SchedulerSlot:
        with self._lock:
            return self.slot

    def try_claim_lease(
        self,
        experiment_id: ExperimentId,
        owner_token: str,
        *,
        expected_revision: int,
        now_epoch_us: int,
        lease_until_epoch_us: int,
    ) -> SchedulerLease | None:
        with self._lock:
            if (
                self.slot.revision != expected_revision
                or self.slot.owner_token is not None
            ):
                return None
            lease = SchedulerLease(
                experiment_id=experiment_id,
                owner_token=owner_token,
                lease_until_epoch_us=lease_until_epoch_us,
                acquired_at_epoch_us=now_epoch_us,
                renewed_at_epoch_us=now_epoch_us,
                revision=expected_revision + 1,
            )
            self.slot = SchedulerSlot(
                "global",
                experiment_id,
                owner_token,
                lease_until_epoch_us,
                now_epoch_us,
                now_epoch_us,
                lease.revision,
            )
            return lease

    def release_lease(
        self,
        lease: SchedulerLease,
        *,
        now_epoch_us: int,
    ) -> SchedulerSlot:
        with self._lock:
            self.release_calls += 1
            if self.release_error is not None:
                raise self.release_error
            self.slot = SchedulerSlot(
                "global",
                None,
                None,
                None,
                self.slot.acquired_at_epoch_us,
                now_epoch_us,
                lease.revision + 1,
            )
            return self.slot


class _PausingAcquireLeaseAuthority(LeaseAuthority):
    """Pause the first acquire so a competing owner can attempt to interleave."""

    def __init__(
        self,
        store: ExperimentSchedulerStoreProtocol,
        *,
        before_acquire: Event,
        resume_acquire: Event,
    ) -> None:
        super().__init__(
            store,
            owner_token="interleaving-control",
            lease_duration=timedelta(minutes=5),
            clock=lambda: _NOW,
        )
        self._before_acquire = before_acquire
        self._resume_acquire = resume_acquire
        self._pause_lock = Lock()
        self._pause_once = True

    def acquire(
        self,
        experiment_id: ExperimentId,
        *,
        expected_revision: int,
    ) -> bool:
        with self._pause_lock:
            pause = self._pause_once
            self._pause_once = False
        if pause:
            self._before_acquire.set()
            if not self._resume_acquire.wait(timeout=5):
                raise AssertionError("control acquire was not resumed")
        return super().acquire(
            experiment_id,
            expected_revision=expected_revision,
        )


class _RetryRecovery:
    """Return or raise the exact operator outcome selected by one test."""

    def __init__(
        self,
        *,
        result: ExperimentControlReceipt | None = None,
        error: BaseException | None = None,
    ) -> None:
        self.result = result
        self.error = error

    def retry_fold(
        self,
        **_kwargs: object,
    ) -> ExperimentControlReceipt:
        if self.error is not None:
            raise self.error
        assert self.result is not None
        return self.result


def _retry(
    authority: LeaseAuthority,
    recovery: _RetryRecovery,
    *,
    store: ExperimentSchedulerStoreProtocol,
) -> ExperimentControlReceipt:
    return retry_fold_under_transient_lease(
        store=store,
        authority=authority,
        recovery=cast(ExperimentRecoveryOrchestrator, recovery),
        request=RetryFoldControlRequest(
            experiment_id=str(_EXPERIMENT_ID),
            candidate_id="candidate-1",
            fold_id="fold-1",
            expected_revision=1,
            occurred_at=_NOW,
        ),
    )


def _authority(store: ExperimentSchedulerStoreProtocol) -> LeaseAuthority:
    return LeaseAuthority(
        store,
        owner_token="control-owner",
        lease_duration=timedelta(minutes=5),
        clock=lambda: _NOW,
    )


class TestControlOnlyFirstAttemptFactory:
    """Placeholder factory fails loudly; control routes never invoke it."""

    def test_create_raises_typed_process_error(self) -> None:
        factory = ControlOnlyFirstAttemptFactory()
        with pytest.raises(AppProcessError) as info:
            factory.create(cast(FoldView, MagicMock(spec=FoldView)), _NOW)
        details = info.value.details
        assert details["code"] == CONTROL_ONLY_FACTORY_CODE
        assert details["reason"] == CONTROL_ONLY_FACTORY_REASON

    def test_create_successor_raises_typed_process_error(self) -> None:
        factory = ControlOnlyFirstAttemptFactory()
        with pytest.raises(AppProcessError) as info:
            factory.create_successor(
                cast(FoldView, MagicMock(spec=FoldView)),
                cast(AttemptView, MagicMock(spec=AttemptView)),
                resume_from_run_id=None,
                occurred_at=_NOW,
            )
        details = info.value.details
        assert details["code"] == CONTROL_ONLY_FACTORY_CODE
        assert details["reason"] == CONTROL_ONLY_FACTORY_REASON


class TestLoggingExperimentControlNotifier:
    """Best-effort notifier must never raise; receipt is already durable."""

    def test_notify_run_stop_does_not_raise(self) -> None:
        notifier = LoggingExperimentControlNotifier()
        notifier.notify_run_stop(
            experiment_id="experiment-1",
            run_id="run-1",
            desired_state="pause",
            occurred_at=_NOW,
        )

    def test_notify_scheduler_does_not_raise(self) -> None:
        notifier = LoggingExperimentControlNotifier()
        notifier.notify_scheduler(
            experiment_id="experiment-1",
            action="resume",
            occurred_at=_NOW,
        )


class TestRetryFoldUnderTransientLease:
    """Release only helper-owned leases without hiding operator failures."""

    def test_serializes_ownership_against_concurrent_same_experiment_acquire(
        self,
    ) -> None:
        store = _ControlStore()
        store_port = cast(ExperimentSchedulerStoreProtocol, store)
        before_control_acquire = Event()
        resume_control_acquire = Event()
        lifecycle_attempting = Event()
        lifecycle_acquired = Event()
        authority = _PausingAcquireLeaseAuthority(
            store_port,
            before_acquire=before_control_acquire,
            resume_acquire=resume_control_acquire,
        )

        def acquire_lifecycle_lease() -> None:
            lifecycle_attempting.set()
            for _attempt in range(3):
                slot = store.get_scheduler_slot()
                if authority.acquire(
                    _EXPERIMENT_ID,
                    expected_revision=slot.revision,
                ):
                    lifecycle_acquired.set()
                    return
            raise AssertionError("lifecycle lease could not be acquired")

        with ThreadPoolExecutor(max_workers=2) as executor:
            control_future = executor.submit(
                _retry,
                authority,
                _RetryRecovery(result=_RECEIPT),
                store=store_port,
            )
            assert before_control_acquire.wait(timeout=5)
            lifecycle_future = executor.submit(acquire_lifecycle_lease)
            assert lifecycle_attempting.wait(timeout=5)
            interleaved = lifecycle_acquired.wait(timeout=0.25)
            resume_control_acquire.set()
            assert control_future.result(timeout=5) is _RECEIPT
            lifecycle_future.result(timeout=5)

        assert interleaved is False
        assert authority.has_lease is True
        assert store.release_calls == 1

    def test_preserves_preexisting_scheduler_lease(self) -> None:
        store = _ControlStore()
        store_port = cast(ExperimentSchedulerStoreProtocol, store)
        authority = _authority(store_port)
        assert authority.acquire(_EXPERIMENT_ID, expected_revision=0)

        receipt = _retry(
            authority,
            _RetryRecovery(result=_RECEIPT),
            store=store_port,
        )

        assert receipt is _RECEIPT
        assert store.release_calls == 0
        assert authority.has_lease is True

    def test_preserves_operator_error_when_transient_release_also_fails(self) -> None:
        operator_error = AppProcessError(
            "operator request rejected",
            details={"code": "SPEC_INVALID", "reason": "stale_fold_revision"},
        )
        release_error = AppProcessError(
            "release rejected",
            details={"code": "SPEC_INVALID", "reason": "release_rejected"},
        )
        store = _ControlStore(release_error=release_error)
        store_port = cast(ExperimentSchedulerStoreProtocol, store)
        authority = _authority(store_port)

        with pytest.raises(AppProcessError) as exc_info:
            _retry(
                authority,
                _RetryRecovery(error=operator_error),
                store=store_port,
            )

        assert exc_info.value is operator_error
        assert store.release_calls == 1
        assert any(
            "transient scheduler lease release also failed" in note
            for note in getattr(operator_error, "__notes__", ())
        )

    def test_surfaces_transient_release_error_after_success(self) -> None:
        release_error = AppProcessError(
            "release rejected",
            details={"code": "SPEC_INVALID", "reason": "release_rejected"},
        )
        store = _ControlStore(release_error=release_error)
        store_port = cast(ExperimentSchedulerStoreProtocol, store)
        authority = _authority(store_port)

        with pytest.raises(AppProcessError) as exc_info:
            _retry(
                authority,
                _RetryRecovery(result=_RECEIPT),
                store=store_port,
            )

        assert exc_info.value is release_error
        assert store.release_calls == 1
