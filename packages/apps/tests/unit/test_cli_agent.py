"""Contract tests for the governed Agent CLI surface."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import MagicMock

import orjson
import pytest
from ditto_agent.contracts.runtime import ModelProfile, RetentionClass, RunStatus
from ditto_agent.runtime.service import (
    AgentApprovalDecision,
    AgentEventView,
    AgentResourceNotFound,
    AgentRuntimePort,
    AgentRuntimeUnavailable,
    AgentRunView,
    AgentSessionView,
    ApprovalDecisionStatus,
)
from ditto_apps.cli.commands import agent
from ditto_apps.cli.main import app as main_app
from typer.testing import CliRunner

_NOW = datetime(2026, 8, 16, 2, 3, 4, tzinfo=UTC)
_HASH_A = "a" * 64
_HASH_B = "b" * 64
_HASH_C = "c" * 64


def _session() -> AgentSessionView:
    return AgentSessionView(
        session_id="session-1",
        created_at=_NOW,
        retention_class=RetentionClass.STANDARD,
    )


def _run(
    *,
    status: RunStatus = RunStatus.QUEUED,
    revision: int = 0,
) -> AgentRunView:
    finished_at = (
        _NOW
        if status in {RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.CANCELLED}
        else None
    )
    return AgentRunView(
        run_id="run-1",
        session_id="session-1",
        status=status,
        objective_hash=_HASH_A,
        authority_hash=_HASH_B,
        max_model_tokens=4096,
        max_model_spend_usd=Decimal("0.25"),
        model_profile=ModelProfile.BALANCED,
        manifest_hash=_HASH_C,
        created_at=_NOW,
        started_at=_NOW if revision else None,
        finished_at=finished_at,
        revision=revision,
    )


def _event(event_id: int, event_type: str) -> AgentEventView:
    return AgentEventView(
        event_id=event_id,
        run_id="run-1",
        run_sequence=event_id,
        event_type=event_type,
        payload_hash=_HASH_A,
        occurred_at=_NOW,
        prev_hash=None if event_id == 1 else _HASH_B,
        event_hash=_HASH_C,
    )


def _approval() -> AgentApprovalDecision:
    return AgentApprovalDecision(
        approval_id="approval-1",
        run_id="run-1",
        action_hash=_HASH_A,
        status=ApprovalDecisionStatus.APPROVED,
        operator_id="operator-1",
        reason="reviewed",
        decided_at=_NOW,
    )


def _install_runtime(
    monkeypatch: pytest.MonkeyPatch,
    runtime: MagicMock,
) -> MagicMock:
    container = MagicMock()
    container.get.return_value = runtime
    monkeypatch.setattr(agent, "make_app_container", MagicMock(return_value=container))
    return container


def test_agent_help_registers_fixed_r51_command_surface() -> None:
    runner = CliRunner()

    result = runner.invoke(main_app, ["agent", "--help"])

    assert result.exit_code == 0, result.output
    for command in ("run", "show", "events", "cancel", "approve", "reject"):
        assert command in result.stdout
    events_help = runner.invoke(main_app, ["agent", "events", "--help"])
    assert events_help.exit_code == 0, events_help.output
    assert "--follow" in events_help.stdout
    assert "--after-event-id" in events_help.stdout


def test_run_reuses_runtime_for_session_and_run_without_echoing_objective(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = MagicMock(spec=AgentRuntimePort)
    runtime.create_session.return_value = _session()
    runtime.create_run.return_value = _run()
    container = _install_runtime(monkeypatch, runtime)

    result = CliRunner().invoke(
        main_app,
        [
            "agent",
            "run",
            "secret research objective",
            "--authority-hash",
            _HASH_B,
            "--idempotency-key",
            "request-1",
            "--max-model-spend-usd",
            "0.25",
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    session_command = runtime.create_session.call_args.args[0]
    run_command = runtime.create_run.call_args.args[0]
    assert session_command.idempotency_key == "request-1:session"
    assert run_command.idempotency_key == "request-1:run"
    assert run_command.session_id == "session-1"
    assert run_command.objective == "secret research objective"
    assert run_command.authority_hash == _HASH_B
    assert run_command.max_model_spend_usd == Decimal("0.25")
    payload = orjson.loads(result.stdout)
    assert payload["session"]["session_id"] == "session-1"
    assert payload["run"]["run_id"] == "run-1"
    assert "secret research objective" not in result.stdout
    container.get.assert_called_once_with(AgentRuntimePort)
    container.close.assert_called_once_with()


def test_show_supports_stable_human_and_json_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = MagicMock(spec=AgentRuntimePort)
    runtime.get_run.return_value = _run(status=RunStatus.RUNNING, revision=1)
    _install_runtime(monkeypatch, runtime)

    human = CliRunner().invoke(main_app, ["agent", "show", "run-1"])
    structured = CliRunner().invoke(main_app, ["agent", "show", "run-1", "--json"])

    assert human.exit_code == 0, human.output
    assert human.stdout == "run_id=run-1 status=running revision=1\n"
    assert structured.exit_code == 0, structured.output
    assert orjson.loads(structured.stdout)["objective_hash"] == _HASH_A


def test_disabled_and_missing_runtime_fail_with_stable_exit_codes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = MagicMock(spec=AgentRuntimePort)
    runtime.get_run.side_effect = AgentRuntimeUnavailable("agent_feature_disabled")
    _install_runtime(monkeypatch, runtime)

    disabled = CliRunner().invoke(main_app, ["agent", "show", "run-1", "--json"])

    assert disabled.exit_code == 3
    assert orjson.loads(disabled.stderr) == {
        "error": {
            "code": "AGENT_FEATURE_DISABLED",
            "message": "Agent runtime is unavailable",
        }
    }

    runtime.get_run.side_effect = AgentResourceNotFound(
        "Agent run does not exist",
        reason_code="agent_run_missing",
    )
    missing = CliRunner().invoke(main_app, ["agent", "show", "missing"])
    assert missing.exit_code == 4
    assert missing.stderr == "AGENT_RUN_MISSING: Agent run does not exist\n"


def test_runtime_resolution_failure_is_structured_and_does_not_leak_details(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        agent,
        "make_app_container",
        MagicMock(side_effect=RuntimeError("secret-provider-detail")),
    )

    result = CliRunner().invoke(main_app, ["agent", "show", "run-1", "--json"])

    assert result.exit_code == 3
    assert orjson.loads(result.stderr)["error"]["code"] == (
        "AGENT_RUNTIME_RESOLUTION_FAILED"
    )
    assert "secret-provider-detail" not in result.output


def test_invalid_spend_budget_fails_before_session_write(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = MagicMock(spec=AgentRuntimePort)
    container = _install_runtime(monkeypatch, runtime)

    result = CliRunner().invoke(
        main_app,
        [
            "agent",
            "run",
            "objective",
            "--authority-hash",
            _HASH_B,
            "--idempotency-key",
            "request-1",
            "--max-model-spend-usd",
            "NaN",
            "--json",
        ],
    )

    assert result.exit_code == 2
    assert orjson.loads(result.stderr)["error"]["code"] == "AGENT_REQUEST_INVALID"
    runtime.create_session.assert_not_called()
    container.close.assert_called_once_with()


def test_events_resume_reads_only_events_after_cursor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = MagicMock(spec=AgentRuntimePort)
    runtime.list_run_events.return_value = (_event(8, "tool_completed"),)
    _install_runtime(monkeypatch, runtime)

    result = CliRunner().invoke(
        main_app,
        [
            "agent",
            "events",
            "run-1",
            "--after-event-id",
            "7",
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    runtime.list_run_events.assert_called_once_with("run-1", after_event_id=7)
    runtime.create_run.assert_not_called()
    assert orjson.loads(result.stdout)["events"][0]["event_id"] == 8


def test_events_follow_advances_persisted_cursor_without_starting_a_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = MagicMock(spec=AgentRuntimePort)
    runtime.list_run_events.side_effect = (
        (_event(1, "run_queued"),),
        (_event(2, "run_completed"),),
    )
    runtime.get_run.side_effect = (
        _run(status=RunStatus.RUNNING, revision=1),
        _run(status=RunStatus.COMPLETED, revision=2),
    )
    _install_runtime(monkeypatch, runtime)

    result = CliRunner().invoke(
        main_app,
        [
            "agent",
            "events",
            "run-1",
            "--follow",
            "--poll-interval",
            "0",
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    assert runtime.list_run_events.call_args_list[0].kwargs == {"after_event_id": None}
    assert runtime.list_run_events.call_args_list[1].kwargs == {"after_event_id": 1}
    runtime.create_session.assert_not_called()
    runtime.create_run.assert_not_called()
    assert [orjson.loads(line)["event_id"] for line in result.stdout.splitlines()] == [
        1,
        2,
    ]


def test_cancel_preserves_revision_fence_and_outputs_receipt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = MagicMock(spec=AgentRuntimePort)
    runtime.cancel_run.return_value = _run(status=RunStatus.CANCELLED, revision=1)
    _install_runtime(monkeypatch, runtime)

    result = CliRunner().invoke(
        main_app,
        [
            "agent",
            "cancel",
            "run-1",
            "--expected-revision",
            "0",
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    command = runtime.cancel_run.call_args.args[0]
    assert command.run_id == "run-1"
    assert command.expected_revision == 0
    assert orjson.loads(result.stdout)["status"] == "cancelled"


def test_approve_and_reject_bind_exact_action_hash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = MagicMock(spec=AgentRuntimePort)
    runtime.decide_approval.return_value = _approval()
    _install_runtime(monkeypatch, runtime)
    runner = CliRunner()

    approved = runner.invoke(
        main_app,
        [
            "agent",
            "approve",
            "approval-1",
            "--expected-action-hash",
            _HASH_A,
            "--operator-id",
            "operator-1",
            "--reason",
            "reviewed",
            "--json",
        ],
    )
    rejected = runner.invoke(
        main_app,
        [
            "agent",
            "reject",
            "approval-1",
            "--expected-action-hash",
            _HASH_A,
            "--operator-id",
            "operator-1",
        ],
    )

    assert approved.exit_code == 0, approved.output
    assert rejected.exit_code == 0, rejected.output
    approve_command = runtime.decide_approval.call_args_list[0].args[0]
    reject_command = runtime.decide_approval.call_args_list[1].args[0]
    assert approve_command.decision.value == "approve"
    assert reject_command.decision.value == "reject"
    assert approve_command.expected_action_hash == _HASH_A
    assert orjson.loads(approved.stdout)["status"] == "approved"
