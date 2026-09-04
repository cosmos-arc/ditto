"""PAP-06 EOD job recovery and reconciliation behavior."""

from __future__ import annotations

from unittest.mock import Mock

import pytest
from ditto_apps.jobs.paper_eod import PaperEodJob
from ditto_platform.foundation import Metrics


def test_eod_recovers_then_reconciles() -> None:
    operator = Mock()
    operator.recover.return_value = (Mock(),)
    handler = Mock()
    handler.reconcile.return_value = Mock(balanced=True, checksum="paper-eod:ok")
    job = PaperEodJob(operator=operator, command_handler=handler)

    result = job.run(
        session_id="session-1",
        idempotency_key="eod-1",
    )

    operator.recover.assert_called_once_with("session-1")
    assert result.reconciliation_checksum == "paper-eod:ok"
    assert result.recovered_execution_count == 1


def test_eod_fails_closed_on_unbalanced_reconciliation() -> None:
    operator = Mock()
    operator.recover.return_value = ()
    handler = Mock()
    handler.reconcile.return_value = Mock(balanced=False, checksum="paper-eod:bad")
    job = PaperEodJob(operator=operator, command_handler=handler)

    with pytest.raises(RuntimeError, match="unbalanced"):
        job.run(session_id="session-1", idempotency_key="eod-1")


def test_eod_records_completed_and_unbalanced_operational_metrics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    counter = Mock()
    monkeypatch.setattr(Metrics, "workstation_paper_eod", counter, raising=False)
    operator = Mock()
    operator.recover.return_value = ()
    handler = Mock()
    job = PaperEodJob(operator=operator, command_handler=handler)

    handler.reconcile.return_value = Mock(balanced=True, checksum="ok")
    job.run(session_id="session-1", idempotency_key="eod-1")
    handler.reconcile.return_value = Mock(balanced=False, checksum="bad")
    with pytest.raises(RuntimeError, match="unbalanced"):
        job.run(session_id="session-1", idempotency_key="eod-2")

    assert counter.add.call_args_list == [
        ((1,), {"attributes": {"status": "completed"}}),
        ((1,), {"attributes": {"status": "unbalanced"}}),
    ]
