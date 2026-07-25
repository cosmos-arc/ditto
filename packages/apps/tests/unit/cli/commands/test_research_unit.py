"""Unit tests for research CLI command payload helpers."""

from __future__ import annotations

from datetime import UTC, datetime

from ditto_application.processes.experiments._coordinator_contract import (
    ExperimentControlReceipt,
)
from ditto_apps.cli.commands.research import _receipt_payload


def test_receipt_payload_maps_control_receipt_fields() -> None:
    receipt = ExperimentControlReceipt(
        experiment_id="exp-1",
        status="pause_requested",
        desired_state="pause",
        revision=2,
        occurred_at=datetime(2026, 7, 25, 0, 0, 0, tzinfo=UTC),
        live_run_ids=("run-1", "run-2"),
    )

    payload = _receipt_payload(receipt)

    assert payload["experiment_id"] == "exp-1"
    assert payload["status"] == "pause_requested"
    assert payload["desired_state"] == "pause"
    assert payload["revision"] == 2
    assert payload["occurred_at"] == "2026-07-25T00:00:00+00:00"
    assert payload["live_run_ids"] == ["run-1", "run-2"]
