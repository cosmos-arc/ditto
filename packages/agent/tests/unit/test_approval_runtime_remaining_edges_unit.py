"""Fail-closed edge coverage for the durable approval runtime."""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from typing import cast

import orjson
import pytest
from ditto_agent._canonical import canonical_bytes, canonical_sha256
from ditto_agent.approval_codec import ModelRequestIdentity, ResumeEnvelope
from ditto_agent.approval_runtime import (
    AgentApprovalRuntime,
    ApprovalRuntimeConflict,
    ApprovalRuntimeSettings,
    ApprovalRuntimeUnavailable,
    ApprovalRuntimeViolation,
    _ReadyResume,
)
from ditto_agent.contracts.approval import ApprovalRequest
from ditto_agent.contracts.runtime import RunStatus
from ditto_agent.models.port import (
    ModelContinuation,
    ModelRequest,
    ModelToolSpec,
)
from ditto_agent.storage.sqlite.database import AgentDatabase
from ditto_agent.storage.sqlite.errors import AgentPersistenceError
from ditto_agent.storage.sqlite.reader import AgentStoreReader
from ditto_agent.storage.sqlite.records import StoredAgentRun
from ditto_agent.storage.sqlite.writer import AgentStoreWriter
from packages.agent.tests.unit import test_approval_runtime as fixtures


@pytest.mark.parametrize(
    ("approval_ttl", "lease_ttl", "provider_timeout", "message"),
    [
        (timedelta(0), timedelta(minutes=2), timedelta(seconds=30), "approval_ttl"),
        (timedelta(minutes=1), timedelta(0), timedelta(seconds=30), "resume_lease"),
        (timedelta(minutes=1), timedelta(minutes=2), timedelta(0), "provider_timeout"),
        (
            timedelta(minutes=1),
            timedelta(minutes=2),
            timedelta(minutes=2),
            "shorter",
        ),
    ],
)
def test_settings_reject_nonpositive_or_unbounded_windows(
    approval_ttl: timedelta,
    lease_ttl: timedelta,
    provider_timeout: timedelta,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        ApprovalRuntimeSettings(
            approval_ttl=approval_ttl,
            resume_lease_ttl=lease_ttl,
            provider_timeout=provider_timeout,
        )


@pytest.mark.parametrize(
    ("drift", "reason_code"),
    [
        ("tool", "agent_approval_action_mismatch"),
        ("arguments", "agent_approval_arguments_mismatch"),
        ("authority", "agent_approval_authority_mismatch"),
        ("tokens", "agent_approval_budget_exceeded"),
        ("spend", "agent_approval_budget_exceeded"),
    ],
)
def test_action_validation_rejects_every_host_binding_drift(
    drift: str,
    reason_code: str,
) -> None:
    interruption = fixtures._interrupted().interruptions[0]
    resolver = fixtures._ActionResolver()
    action = resolver.resolve(
        run_id="run-r52",
        interruption=interruption,
        expires_at=fixtures.NOW + timedelta(minutes=15),
    )
    if drift == "tool":
        action = replace(action, tool_name="other_tool")
    elif drift == "arguments":
        action = replace(action, parameters={"strategy_id": "different"})
    elif drift == "authority":
        action = replace(action, authority_hash=fixtures.HASH_B)
    elif drift == "tokens":
        action = replace(
            action,
            budget=replace(action.budget, max_model_tokens=513),
        )
    else:
        action = replace(
            action,
            budget=replace(action.budget, max_model_spend_usd=Decimal("0.21")),
        )

    with pytest.raises(ApprovalRuntimeViolation) as exc_info:
        AgentApprovalRuntime._validate_action(
            run_authority_hash=fixtures.HASH_A,
            interruption=interruption,
            action=action,
            max_model_tokens=512,
            max_model_spend_usd=Decimal("0.20"),
        )

    assert exc_info.value.reason_code == reason_code


def test_suspend_rejects_missing_or_nonrunning_run(tmp_path: Path) -> None:
    runtime, _database, reader, writer, *_rest = fixtures._runtime(tmp_path)

    with pytest.raises(ApprovalRuntimeConflict) as missing:
        runtime.suspend(
            request=fixtures._request("missing-run"),
            result=fixtures._interrupted(),
        )
    assert missing.value.reason_code == "agent_run_missing"

    running = reader.get_run("run-r52")
    assert running is not None
    writer.transition_run(
        run_id=running.run_id,
        expected_revision=running.revision,
        target=RunStatus.PAUSED,
        occurred_at=fixtures.NOW,
    )
    with pytest.raises(ApprovalRuntimeConflict) as paused:
        runtime.suspend(request=fixtures._request(), result=fixtures._interrupted())
    assert paused.value.reason_code == "agent_run_state_conflict"


@pytest.mark.parametrize("tool_state", ["missing", "not_approvable"])
def test_suspend_rejects_unregistered_or_unapproved_tool(
    tmp_path: Path,
    tool_state: str,
) -> None:
    runtime, *_rest = fixtures._runtime(tmp_path)
    request = fixtures._request()
    if tool_state == "missing":
        request = replace(request, tools=())
    else:
        request = replace(
            request,
            tools=(replace(fixtures._tool(), requires_approval=False),),
        )

    with pytest.raises(ApprovalRuntimeViolation) as exc_info:
        runtime.suspend(request=request, result=fixtures._interrupted())
    assert exc_info.value.reason_code == "agent_approval_tool_not_allowed"


def test_suspend_rejects_oversized_continuation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime, *_rest = fixtures._runtime(tmp_path)
    monkeypatch.setattr("ditto_agent.approval_runtime.MAX_CONTINUATION_BYTES", 1)

    with pytest.raises(ApprovalRuntimeViolation) as exc_info:
        runtime.suspend(request=fixtures._request(), result=fixtures._interrupted())
    assert exc_info.value.reason_code == "agent_continuation_too_large"


def _rewrite_continuation(
    database: AgentDatabase,
    *,
    payload_changes: dict[str, object] | None = None,
    continuation_changes: dict[str, object] | None = None,
) -> None:
    connection = database.get_connection()
    row = connection.execute(
        "SELECT payload_json FROM agent_run_continuations WHERE run_id=?",
        ("run-r52",),
    ).fetchone()
    assert row is not None
    payload = orjson.loads(bytes(row[0]))
    assert isinstance(payload, dict)
    payload.update(payload_changes or {})
    continuation = payload["continuation"]
    assert isinstance(continuation, dict)
    continuation.update(continuation_changes or {})
    replacement = canonical_bytes(payload)
    connection.execute(
        """
        UPDATE agent_run_continuations
        SET payload_json=?, payload_hash=? WHERE run_id=?
        """,
        (replacement, canonical_sha256(payload), "run-r52"),
    )
    connection.commit()


def test_load_envelope_rejects_missing_run_and_provider_drift(tmp_path: Path) -> None:
    runtime, database, *_rest = fixtures._runtime(tmp_path)
    with pytest.raises(ApprovalRuntimeConflict) as missing:
        runtime._load_envelope("run-r52")
    assert missing.value.reason_code == "agent_continuation_missing"

    runtime.suspend(request=fixtures._request(), result=fixtures._interrupted())
    _rewrite_continuation(database, payload_changes={"run_id": "other-run"})
    with pytest.raises(ApprovalRuntimeViolation) as run_drift:
        runtime._load_envelope("run-r52")
    assert run_drift.value.reason_code == "agent_continuation_run_mismatch"


def test_load_envelope_rejects_provider_drift(tmp_path: Path) -> None:
    runtime, database, *_rest = fixtures._runtime(tmp_path)
    runtime.suspend(request=fixtures._request(), result=fixtures._interrupted())
    _rewrite_continuation(database, continuation_changes={"provider": "other-provider"})

    with pytest.raises(ApprovalRuntimeViolation) as exc_info:
        runtime._load_envelope("run-r52")
    assert exc_info.value.reason_code == "agent_continuation_provider_mismatch"


@pytest.mark.parametrize("resolver_result", [None, fixtures._request("other-run")])
def test_resolve_request_rejects_missing_or_foreign_request(
    tmp_path: Path,
    resolver_result: object,
) -> None:
    runtime, *_rest = fixtures._runtime(tmp_path)
    runtime._request_resolver = lambda _run_id: cast(
        ModelRequest | None, resolver_result
    )

    with pytest.raises(ApprovalRuntimeConflict) as exc_info:
        runtime._resolve_request(
            "run-r52",
            ModelRequestIdentity.from_request(fixtures._request()),
        )
    assert exc_info.value.reason_code == "agent_resume_request_missing"


def _pending_state(
    tmp_path: Path,
) -> tuple[
    AgentApprovalRuntime,
    AgentDatabase,
    AgentStoreReader,
    AgentStoreWriter,
    ApprovalRequest,
    tuple[StoredAgentRun, ResumeEnvelope],
]:
    runtime, database, reader, writer, *_rest = fixtures._runtime(tmp_path)
    batch = runtime.suspend(request=fixtures._request(), result=fixtures._interrupted())
    envelope, _hash = runtime._load_envelope("run-r52")
    run = reader.get_run("run-r52")
    assert run is not None
    return runtime, database, reader, writer, batch.approvals[0], (run, envelope)


@pytest.mark.parametrize("drift", ["missing", "binding", "payload", "tool", "expiry"])
def test_validated_decision_rejects_durable_identity_drift(
    tmp_path: Path,
    drift: str,
) -> None:
    runtime, database, _reader, _writer, approval, state = _pending_state(tmp_path)
    run, envelope = state
    binding = envelope.interruptions[0]
    tools: dict[str, ModelToolSpec] = {fixtures._tool().name: fixtures._tool()}
    now = fixtures.NOW
    connection = database.get_connection()
    if drift == "missing":
        connection.execute(
            "DELETE FROM agent_approvals WHERE request_id=?", (approval.request_id,)
        )
    elif drift == "binding":
        binding = replace(binding, action_hash=fixtures.HASH_B)
    elif drift == "payload":
        row = connection.execute(
            "SELECT action_payload FROM agent_approvals WHERE request_id=?",
            (approval.request_id,),
        ).fetchone()
        assert row is not None
        payload = orjson.loads(bytes(row[0]))
        payload["subject_identity"] = "strategy-drifted"
        connection.execute(
            "UPDATE agent_approvals SET action_payload=? WHERE request_id=?",
            (canonical_bytes(payload), approval.request_id),
        )
    elif drift == "tool":
        tools = {}
    else:
        now = fixtures.NOW + timedelta(minutes=15)
    connection.commit()

    with pytest.raises(ApprovalRuntimeViolation):
        runtime._validated_decision(
            run_id="run-r52",
            run=run,
            binding=binding,
            tools=tools,
            now=now,
        )


def test_validated_decisions_rejects_missing_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime, _database, reader, _writer, _approval, state = _pending_state(tmp_path)
    _run, envelope = state
    monkeypatch.setattr(reader, "get_run", lambda _run_id: None)

    with pytest.raises(ApprovalRuntimeConflict) as exc_info:
        runtime._validated_decisions(
            run_id="run-r52",
            envelope=envelope,
            request=fixtures._request(),
            now=fixtures.NOW,
        )
    assert exc_info.value.reason_code == "agent_run_missing"


@pytest.mark.asyncio
async def test_completed_resume_is_idempotent_but_missing_active_state_is_not(
    tmp_path: Path,
) -> None:
    runtime, *_rest = fixtures._runtime(tmp_path)
    batch = runtime.suspend(request=fixtures._request(), result=fixtures._interrupted())
    approval = batch.approvals[0]
    outcome = await runtime.decide_and_resume(
        request_id=approval.request_id,
        expected_action_hash=approval.action_hash,
        approved=True,
        operator_id="operator-r52",
        reason=None,
    )
    assert outcome.resumed is True
    assert await runtime.resume_ready("run-r52") is False

    fresh, *_fresh_rest = fixtures._runtime(tmp_path / "fresh")
    with pytest.raises(ApprovalRuntimeConflict) as exc_info:
        await fresh.resume_ready("run-r52")
    assert exc_info.value.reason_code == "agent_continuation_missing"


def test_preflight_rejects_approval_removed_from_active_binding(tmp_path: Path) -> None:
    runtime, database, _reader, _writer, approval, _state = _pending_state(tmp_path)
    connection = database.get_connection()
    row = connection.execute(
        "SELECT payload_json FROM agent_run_continuations WHERE run_id=?",
        ("run-r52",),
    ).fetchone()
    assert row is not None
    payload = orjson.loads(bytes(row[0]))
    payload["interruptions"][0]["request_id"] = "approval-unbound"
    replacement = canonical_bytes(payload)
    connection.execute(
        """
        UPDATE agent_run_continuations
        SET payload_json=?, payload_hash=? WHERE run_id=?
        """,
        (replacement, canonical_sha256(payload), "run-r52"),
    )
    connection.commit()

    with pytest.raises(ApprovalRuntimeViolation) as exc_info:
        runtime._preflight_decision(
            request_id=approval.request_id,
            expected_action_hash=approval.action_hash,
            now=fixtures.NOW,
        )
    assert exc_info.value.reason_code == "agent_approval_binding_mismatch"


def test_resume_lease_storage_failure_is_typed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime, _database, _reader, writer, *_rest = fixtures._runtime(tmp_path)

    def fail(**_kwargs: object) -> None:
        raise AgentPersistenceError("unavailable", reason_code="agent_write_failed")

    monkeypatch.setattr(writer, "try_acquire_lease", fail)
    with pytest.raises(ApprovalRuntimeUnavailable) as exc_info:
        runtime._acquire_resume_lease(run_id="run-r52", now=fixtures.NOW)
    assert exc_info.value.reason_code == "agent_write_failed"


def _approved_ready(
    tmp_path: Path,
) -> tuple[AgentApprovalRuntime, AgentStoreReader, AgentStoreWriter, _ReadyResume]:
    runtime, _database, reader, writer, *_rest = fixtures._runtime(tmp_path)
    batch = runtime.suspend(request=fixtures._request(), result=fixtures._interrupted())
    approval = batch.approvals[0]
    writer.decide_approval(
        request_id=approval.request_id,
        expected_action_hash=approval.action_hash,
        approved=True,
        operator_id="operator-r52",
        reason=None,
        decided_at=fixtures.NOW,
    )
    ready = runtime._ready_resume("run-r52")
    assert ready is not None
    return runtime, reader, writer, ready


def test_resume_transition_rejects_missing_or_terminal_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime, reader, _writer, ready = _approved_ready(tmp_path)
    stored = reader.get_run("run-r52")
    assert stored is not None
    monkeypatch.setattr(reader, "get_run", lambda _run_id: None)
    with pytest.raises(ApprovalRuntimeConflict) as missing:
        runtime._transition_resume_started(ready)
    assert missing.value.reason_code == "agent_run_missing"

    monkeypatch.setattr(
        reader,
        "get_run",
        lambda _run_id: replace(stored, status=RunStatus.FAILED),
    )
    with pytest.raises(ApprovalRuntimeConflict) as terminal:
        runtime._transition_resume_started(ready)
    assert terminal.value.reason_code == "agent_run_state_conflict"


def test_pause_provider_failure_ignores_nonrunning_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime, reader, writer, ready = _approved_ready(tmp_path)
    monkeypatch.setattr(reader, "get_run", lambda _run_id: None)
    transition_called = False

    def transition(**_kwargs: object) -> None:
        nonlocal transition_called
        transition_called = True

    monkeypatch.setattr(writer, "transition_run", transition)
    runtime._pause_provider_failure(ready)
    assert transition_called is False


@pytest.mark.asyncio
async def test_resume_reinterrupts_with_a_hash_fenced_replacement(
    tmp_path: Path,
) -> None:
    second = replace(
        fixtures._interrupted(call_ids=("call-write-2",)),
        continuation=ModelContinuation(
            provider="scripted",
            payload={"run_id": "run-r52", "pending_call_ids": ["call-write-2"]},
        ),
    )
    runtime, _database, reader, _writer, *_rest = fixtures._runtime(
        tmp_path,
        result=second,
    )
    batch = runtime.suspend(request=fixtures._request(), result=fixtures._interrupted())
    approval = batch.approvals[0]

    outcome = await runtime.decide_and_resume(
        request_id=approval.request_id,
        expected_action_hash=approval.action_hash,
        approved=True,
        operator_id="operator-r52",
        reason=None,
    )

    assert outcome.resumed is True
    waiting = reader.get_run("run-r52")
    assert waiting is not None
    assert waiting.status is RunStatus.WAITING_APPROVAL
    continuation = reader.get_continuation("run-r52")
    assert continuation is not None
    assert continuation.payload_hash != batch.continuation_hash


def test_persist_result_rejects_lost_running_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime, reader, _writer, ready = _approved_ready(tmp_path)
    waiting = reader.get_run("run-r52")
    assert waiting is not None
    monkeypatch.setattr(
        reader,
        "get_run",
        lambda _run_id: replace(waiting, status=RunStatus.CANCELLED),
    )

    with pytest.raises(ApprovalRuntimeConflict) as exc_info:
        runtime._persist_resume_result(
            ready=ready,
            result=fixtures._terminal(),
        )
    assert exc_info.value.reason_code == "agent_run_state_conflict"


@pytest.mark.asyncio
async def test_resume_lease_recheck_and_release_fail_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime, _reader, _writer, ready = _approved_ready(tmp_path)
    lease = runtime._acquire_resume_lease(run_id="run-r52", now=fixtures.NOW)
    assert lease is not None
    monkeypatch.setattr(runtime, "_active_resume", lambda _run_id: None)

    assert await runtime._resume_with_lease(initial=ready, lease=lease) == (
        False,
        None,
    )

    runtime2, _reader2, writer2, ready2 = _approved_ready(tmp_path / "release")
    lease2 = runtime2._acquire_resume_lease(run_id="run-r52", now=fixtures.NOW)
    assert lease2 is not None

    def fail_release(*_args: object, **_kwargs: object) -> None:
        raise AgentPersistenceError("unavailable", reason_code="agent_write_failed")

    monkeypatch.setattr(writer2, "release_lease", fail_release)
    resumed, result = await runtime2._resume_with_lease(
        initial=ready2,
        lease=lease2,
    )
    assert resumed is True
    assert result == fixtures._terminal()


@pytest.mark.asyncio
async def test_try_resume_returns_when_lease_is_owned_elsewhere(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime, _reader, writer, _ready = _approved_ready(tmp_path)
    monkeypatch.setattr(writer, "try_acquire_lease", lambda **_kwargs: None)

    assert await runtime._try_resume(run_id="run-r52") == (False, None)
