"""R3 control-only runtime wiring: best-effort notifier + placeholder factory.

The control routes need a production ``ExperimentControlNotifier`` and a
``FirstAttemptFactory`` to construct ``ExperimentExecutionCoordinator``. In the
R3 single-machine durable-tick model the notifier only logs (the worker already
polls durable ``desired_state``), and control operations never dispatch attempts
so the placeholder factory fails loudly if ever invoked.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
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
_NOW_EPOCH_US = int(_NOW.timestamp() * 1_000_000)
_EXPERIMENT_ID = ExperimentId("experiment-control-runtime")
_RECEIPT = ExperimentControlReceipt(
    experiment_id=str(_EXPERIMENT_ID),
    status="running",
    desired_state="run",
    revision=1,
    occurred_at=_NOW,
)


class _ControlStore:
    """Minimal scheduler slot reader used by transient-lease control tests."""

    def get_scheduler_slot(self) -> SchedulerSlot:
        return SchedulerSlot("global", None, None, None, None, None, 0)


class _ControlAuthority:
    """Exercise helper ownership and cleanup without a persistence backend."""

    def __init__(
        self,
        *,
        has_lease: bool,
        release_error: BaseException | None = None,
    ) -> None:
        self.has_lease = has_lease
        self.release_error = release_error
        self.release_calls = 0
        self._lease = SchedulerLease(
            experiment_id=_EXPERIMENT_ID,
            owner_token="control-owner",
            lease_until_epoch_us=_NOW_EPOCH_US + 300_000_000,
            acquired_at_epoch_us=_NOW_EPOCH_US,
            renewed_at_epoch_us=_NOW_EPOCH_US,
            revision=1,
        )

    def acquire(
        self,
        experiment_id: ExperimentId,
        *,
        expected_revision: int,
    ) -> bool:
        assert experiment_id == _EXPERIMENT_ID
        assert expected_revision == 0
        self.has_lease = True
        return True

    def execute_operator(
        self,
        operation: Callable[
            [SchedulerLease, Callable[[], int]],
            ExperimentControlReceipt,
        ],
    ) -> ExperimentControlReceipt:
        return operation(self._lease, lambda: _NOW_EPOCH_US)

    def release(self) -> SchedulerSlot:
        self.release_calls += 1
        if self.release_error is not None:
            raise self.release_error
        self.has_lease = False
        return SchedulerSlot("global", None, None, None, None, None, 2)


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
    authority: _ControlAuthority,
    recovery: _RetryRecovery,
) -> ExperimentControlReceipt:
    return retry_fold_under_transient_lease(
        store=cast(ExperimentSchedulerStoreProtocol, _ControlStore()),
        authority=cast(LeaseAuthority, authority),
        recovery=cast(ExperimentRecoveryOrchestrator, recovery),
        request=RetryFoldControlRequest(
            experiment_id=str(_EXPERIMENT_ID),
            candidate_id="candidate-1",
            fold_id="fold-1",
            expected_revision=1,
            occurred_at=_NOW,
        ),
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

    def test_preserves_preexisting_scheduler_lease(self) -> None:
        authority = _ControlAuthority(has_lease=True)

        receipt = _retry(authority, _RetryRecovery(result=_RECEIPT))

        assert receipt is _RECEIPT
        assert authority.release_calls == 0
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
        authority = _ControlAuthority(
            has_lease=False,
            release_error=release_error,
        )

        with pytest.raises(AppProcessError) as exc_info:
            _retry(authority, _RetryRecovery(error=operator_error))

        assert exc_info.value is operator_error
        assert authority.release_calls == 1
        assert any(
            "transient scheduler lease release also failed" in note
            for note in getattr(operator_error, "__notes__", ())
        )

    def test_surfaces_transient_release_error_after_success(self) -> None:
        release_error = AppProcessError(
            "release rejected",
            details={"code": "SPEC_INVALID", "reason": "release_rejected"},
        )
        authority = _ControlAuthority(
            has_lease=False,
            release_error=release_error,
        )

        with pytest.raises(AppProcessError) as exc_info:
            _retry(authority, _RetryRecovery(result=_RECEIPT))

        assert exc_info.value is release_error
        assert authority.release_calls == 1
