"""R3 control-only runtime wiring: best-effort notifier + placeholder factory.

The control routes need a production ``ExperimentControlNotifier`` and a
``FirstAttemptFactory`` to construct ``ExperimentExecutionCoordinator``. In the
R3 single-machine durable-tick model the notifier only logs (the worker already
polls durable ``desired_state``), and control operations never dispatch attempts
so the placeholder factory fails loudly if ever invoked.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from threading import Lock, RLock
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

    def __init__(
        self,
        *,
        release_error: BaseException | None = None,
        probe: Callable[[str], None] | None = None,
    ) -> None:
        self.slot = SchedulerSlot("global", None, None, None, None, None, 0)
        self.release_calls = 0
        self.release_error = release_error
        self.probe = probe
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
            if self.probe is not None:
                self.probe("acquire")
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
            if self.probe is not None:
                self.probe("release")
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


class _SpyRLock:
    """Expose nested authority sections while preserving reentrant locking."""

    def __init__(self) -> None:
        self._lock = RLock()
        self.depth = 0
        self.section_id = 0
        self.active_section_id: int | None = None

    def __enter__(self) -> None:
        self._lock.acquire()
        if self.depth == 0:
            self.section_id += 1
            self.active_section_id = self.section_id
        self.depth += 1

    def __exit__(
        self,
        _exc_type: object,
        _exc_value: object,
        _traceback: object,
    ) -> None:
        self.depth -= 1
        if self.depth == 0:
            self.active_section_id = None
        self._lock.release()


class _RetryRecovery:
    """Return or raise the exact operator outcome selected by one test."""

    def __init__(
        self,
        *,
        result: ExperimentControlReceipt | None = None,
        error: BaseException | None = None,
        probe: Callable[[str], None] | None = None,
    ) -> None:
        self.result = result
        self.error = error
        self.probe = probe

    def retry_fold(
        self,
        _request: RetryFoldControlRequest,
        **_kwargs: object,
    ) -> ExperimentControlReceipt:
        if self.probe is not None:
            self.probe("operator")
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

    def test_holds_one_outer_authority_section_across_transient_lifecycle(
        self,
    ) -> None:
        lock = _SpyRLock()
        events: list[tuple[str, int, int | None]] = []

        def probe(event: str) -> None:
            events.append((event, lock.depth, lock.active_section_id))

        store = _ControlStore(probe=probe)
        store_port = cast(ExperimentSchedulerStoreProtocol, store)
        authority = _authority(store_port)
        authority._lock = lock

        receipt = _retry(
            authority,
            _RetryRecovery(result=_RECEIPT, probe=probe),
            store=store_port,
        )

        assert receipt is _RECEIPT
        assert [event for event, _depth, _section_id in events] == [
            "acquire",
            "operator",
            "release",
        ]
        assert all(depth >= 2 for _event, depth, _section_id in events)
        assert len({section_id for _event, _depth, section_id in events}) == 1
        assert events[0][2] is not None
        assert lock.depth == 0
        assert authority.has_lease is False
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
        notes = getattr(operator_error, "__notes__", ())
        assert any(
            "transient scheduler lease release also failed" in note for note in notes
        )
        assert any(
            "code=SPEC_INVALID" in note and "reason=release_rejected" in note
            for note in notes
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

    def test_invalidates_authority_when_base_cleanup_follows_operator_error(
        self,
    ) -> None:
        operator_error = AppProcessError(
            "operator request rejected",
            details={"code": "SPEC_INVALID", "reason": "stale_fold_revision"},
        )
        release_error = KeyboardInterrupt("release interrupted")
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
        assert authority.has_lease is False
        assert authority.is_lost is True
        assert any(
            "KeyboardInterrupt: release interrupted" in note
            for note in getattr(operator_error, "__notes__", ())
        )

    def test_invalidates_authority_when_base_cleanup_follows_success(self) -> None:
        release_error = SystemExit(23)
        store = _ControlStore(release_error=release_error)
        store_port = cast(ExperimentSchedulerStoreProtocol, store)
        authority = _authority(store_port)

        with pytest.raises(SystemExit) as exc_info:
            _retry(
                authority,
                _RetryRecovery(result=_RECEIPT),
                store=store_port,
            )

        assert exc_info.value is release_error
        assert authority.has_lease is False
        assert authority.is_lost is True
