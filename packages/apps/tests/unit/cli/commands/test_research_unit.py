"""Unit tests for research CLI command payload helpers."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from types import MappingProxyType
from unittest.mock import MagicMock

import orjson
import pytest
from ditto_application.processes.experiments._coordinator_contract import (
    ExperimentControlReceipt,
)
from ditto_application.processes.experiments.planning_contracts import (
    ExperimentPreflightCheck,
    PreflightOutcome,
)
from ditto_application.processes.experiments.planning_process import (
    ExperimentLaunchReceipt,
    ExperimentPreflightReport,
    ExperimentPreflightStatus,
)
from ditto_application.queries.experiments import (
    ExperimentCandidateReadModel,
    ExperimentDetailReadModel,
)
from ditto_apps.cli.commands import research
from ditto_apps.cli.commands.research import _receipt_payload, _to_json_value
from typer.testing import CliRunner


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


def test_planning_json_output_rejects_non_string_evidence_keys() -> None:
    with pytest.raises(TypeError, match="mapping key must be exact str"):
        _to_json_value({"nested": {1: "must-not-be-dropped"}})


def _document() -> dict[str, object]:
    return {
        "experiment_id": "exp-1",
        "research_cycle_id": "cycle-1",
        "research_cycle_hash": "a" * 64,
        "strategy": {
            "strategy_id": "strategy-1",
            "version": 2,
            "spec_hash": "b" * 64,
            "spec_json": {"name": "Strategy"},
        },
        "snapshot": {
            "snapshot_id": "snapshot-1",
            "manifest_hash": "c" * 64,
        },
        "validation": {"trading_sessions": ["2026-07-30"]},
        "matrix": {
            "baseline": {
                "descriptor_type": "active-strategy",
                "payload": {"strategy_id": "strategy-1"},
                "schema_version": 1,
            },
            "axes": [
                {
                    "name": "selector.top_k",
                    "values": [{"type": "int", "value": 10}],
                }
            ],
            "candidate_limit": 4,
        },
        "promotion_objective": {
            "schema_id": "r3-promotion-objective",
            "schema_version": 1,
        },
        "dataset_requirements": [
            {
                "dataset_id": "etf_daily",
                "expected_snapshot_ids": ["provider-snapshot-1"],
                "requires_pit_universe": True,
                "certified_from": "2016-01-01",
            }
        ],
        "cost_model": {
            "bytes_per_run": 100,
            "bytes_per_trading_session": 2,
        },
        "budget": {
            "candidate_limit": 4,
            "fold_run_limit": 100,
            "trading_session_limit": 10_000,
            "disk_byte_limit": 1_000_000,
        },
        "seed": 42,
        "worker_count": 2,
        "failure_policy": "fail_fast",
        "created_at": "2026-07-30T00:00:00Z",
    }


def _report() -> ExperimentPreflightReport:
    return ExperimentPreflightReport(
        status=ExperimentPreflightStatus.READY,
        plan_hash="d" * 64,
        checks=(
            ExperimentPreflightCheck(
                "history",
                PreflightOutcome.PASS,
                None,
                None,
                None,
                MappingProxyType({"eligible_month_count": 96}),
                MappingProxyType({"promotion_minimum": 96}),
            ),
        ),
        candidate_count=2,
        planned_fold_count=8,
        budget_run_count=7,
        estimated_trading_sessions=1234,
        estimated_disk_bytes=5678,
        eligible_month_count=96,
        isolation_width_sessions=5,
        validation_plan=None,
        work_plan=None,
    )


def _write_document(path: Path) -> None:
    path.write_bytes(orjson.dumps(_document()))


def test_preflight_document_uses_canonical_builder_and_planning_process(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document_path = tmp_path / "planning.json"
    _write_document(document_path)
    request = MagicMock()
    builder = MagicMock(return_value=request)
    bundle = MagicMock()
    bundle.planning_process.preflight.return_value = _report()
    create_bundle = MagicMock()
    create_bundle.return_value.__enter__.return_value = bundle
    monkeypatch.setattr(research, "build_experiment_planning_request", builder)
    monkeypatch.setattr(research, "create_research_bundle", create_bundle)

    result = CliRunner().invoke(
        research.app,
        ["preflight", "--document", str(document_path)],
    )

    assert result.exit_code == 0, result.output
    builder.assert_called_once_with(_document())
    bundle.planning_process.preflight.assert_called_once_with(request)
    assert orjson.loads(result.stdout)["plan_hash"] == "d" * 64


def test_launch_document_uses_same_builder_and_launch_handler(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document_path = tmp_path / "planning.json"
    _write_document(document_path)
    request = MagicMock()
    builder = MagicMock(return_value=request)
    bundle = MagicMock()
    bundle.launch_handler.handle.return_value = ExperimentLaunchReceipt(
        experiment_id="exp-1",
        status="queued",
        queue_ordinal=3,
        revision=1,
        candidate_count=2,
        fold_count=8,
        plan_hash="d" * 64,
    )
    create_bundle = MagicMock()
    create_bundle.return_value.__enter__.return_value = bundle
    monkeypatch.setattr(research, "build_experiment_planning_request", builder)
    monkeypatch.setattr(research, "create_research_bundle", create_bundle)

    result = CliRunner().invoke(
        research.app,
        [
            "launch",
            "--document",
            str(document_path),
            "--confirmed-plan-hash",
            "d" * 64,
        ],
    )

    assert result.exit_code == 0, result.output
    builder.assert_called_once_with(_document())
    command = bundle.launch_handler.handle.call_args.args[0]
    assert command.request is request
    assert command.confirmed_plan_hash == "d" * 64
    assert orjson.loads(result.stdout) == {
        "experiment_id": "exp-1",
        "status": "queued",
        "queue_ordinal": 3,
        "revision": 1,
        "candidate_count": 2,
        "fold_count": 8,
        "plan_hash": "d" * 64,
    }


def test_get_experiment_serializes_immutable_candidate_parameters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    occurred_at = datetime(2026, 8, 2, 0, 0, 0, tzinfo=UTC)
    detail = ExperimentDetailReadModel(
        experiment_id="exp-live",
        research_cycle_id="cycle-live",
        research_cycle_hash="a" * 64,
        strategy_version="strategy@1",
        strategy_spec_hash="b" * 64,
        snapshot_id="snapshot-live",
        status="running",
        desired_state="run",
        stage="validation",
        failure_code=None,
        queue_ordinal=1,
        revision=3,
        created_at=occurred_at,
        updated_at=occurred_at,
        seed=42,
        worker_count=2,
        failure_policy="fail_fast",
        candidate_limit=4,
        fold_run_limit=128,
        fold_protocol_id="walk-forward",
        fold_protocol_version=1,
        fold_protocol_hash="c" * 64,
        candidates=(
            ExperimentCandidateReadModel(
                candidate_id="candidate-1",
                ordinal=0,
                is_baseline=True,
                parameters=MappingProxyType(
                    {"selector": MappingProxyType({"top_k": 20})}
                ),
            ),
        ),
        folds=(),
    )
    bundle = MagicMock()
    bundle.experiment_query.get.return_value = detail
    create_bundle = MagicMock()
    create_bundle.return_value.__enter__.return_value = bundle
    monkeypatch.setattr(research, "create_research_bundle", create_bundle)

    result = CliRunner().invoke(research.app, ["get-experiment", "exp-live"])

    assert result.exit_code == 0, result.output
    payload = orjson.loads(result.stdout)
    assert payload["candidates"][0]["parameters"] == {"selector": {"top_k": 20}}
    assert payload["created_at"] == "2026-08-02T00:00:00+00:00"
