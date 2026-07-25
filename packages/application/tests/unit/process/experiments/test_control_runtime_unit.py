"""R3 control-only runtime wiring: best-effort notifier + placeholder factory.

The control routes need a production ``ExperimentControlNotifier`` and a
``FirstAttemptFactory`` to construct ``ExperimentExecutionCoordinator``. In the
R3 single-machine durable-tick model the notifier only logs (the worker already
polls durable ``desired_state``), and control operations never dispatch attempts
so the placeholder factory fails loudly if ever invoked.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import cast
from unittest.mock import MagicMock

import pytest
from ditto_analysis.experiments import AttemptView, FoldView
from ditto_application.exceptions import AppProcessError
from ditto_application.processes.experiments._control_runtime import (
    CONTROL_ONLY_FACTORY_CODE,
    CONTROL_ONLY_FACTORY_REASON,
    ControlOnlyFirstAttemptFactory,
    LoggingExperimentControlNotifier,
)

_NOW = datetime(2026, 7, 25, 0, 0, tzinfo=UTC)


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
