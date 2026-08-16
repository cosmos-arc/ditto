from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import cast

import orjson
import pytest
from ditto_agent._canonical import canonical_bytes, canonical_sha256
from ditto_agent.approval_runtime import (
    AgentApprovalRuntime,
    ApprovalRuntimeConflict,
    ApprovalRuntimeSettings,
    ApprovalRuntimeUnavailable,
    ApprovalRuntimeViolation,
)
from ditto_agent.contracts.approval import ActionBudget, ApprovalAction
from ditto_agent.contracts.runtime import (
    AgentManifest,
    AgentRun,
    AgentSession,
    ModelProfile,
    RetentionClass,
    RunStatus,
)
from ditto_agent.contracts.temporal import (
    EgressClass,
    TemporalContextInput,
    TemporalToolContext,
)
from ditto_agent.models.fake import (
    ScriptedAgentModel,
    ScriptedFailure,
    ScriptedOutcome,
)
from ditto_agent.models.port import (
    ModelContinuation,
    ModelFailureKind,
    ModelInterruption,
    ModelRequest,
    ModelResult,
    ModelToolKind,
    ModelToolSpec,
    ModelUsage,
    ResumeModelRequest,
)
from ditto_agent.storage.sqlite.audit import verify_audit_chain
from ditto_agent.storage.sqlite.database import AgentDatabase
from ditto_agent.storage.sqlite.errors import (
    AgentConflictError,
    AgentPersistenceError,
)
from ditto_agent.storage.sqlite.reader import AgentStoreReader
from ditto_agent.storage.sqlite.records import ApprovalStatus
from ditto_agent.storage.sqlite.writer import AgentStoreWriter

NOW = datetime(2026, 8, 16, 8, tzinfo=UTC)
HASH_A = "a" * 64
HASH_B = "b" * 64


class _Clock:
    def __init__(self) -> None:
        self.current = NOW

    def __call__(self) -> datetime:
        return self.current


class _ActionResolver:
    def __init__(self) -> None:
        self.authority_hash = HASH_A
        self.context = _context()
        self.budget = ActionBudget(
            max_tool_calls=1,
            max_output_bytes=16_384,
            max_model_tokens=512,
            max_model_spend_usd=Decimal("0.20"),
        )

    def resolve(
        self,
        *,
        run_id: str,
        interruption: ModelInterruption,
        expires_at: datetime,
    ) -> ApprovalAction:
        del run_id
        return ApprovalAction(
            action_kind="formal_author_write",
            tool_name=interruption.tool_name,
            parameters=interruption.arguments,
            subject_identity=str(interruption.arguments["strategy_id"]),
            required_authority="strategy.author",
            authority_hash=self.authority_hash,
            temporal_context=self.context,
            budget=self.budget,
            expires_at=expires_at,
        )


class _HangingModel(ScriptedAgentModel):
    async def resume(self, request: ResumeModelRequest) -> ModelResult:
        self.requests.append(request)
        await asyncio.Event().wait()
        raise AssertionError("unreachable")


def _context(*, snapshot: str = "snapshot-r52") -> TemporalToolContext:
    return TemporalToolContext.from_host(
        TemporalContextInput(
            decision_time=NOW,
            knowledge_cutoff=NOW - timedelta(minutes=5),
            publication_cutoff=NOW - timedelta(minutes=10),
            source_snapshot_id=snapshot,
            execution_eligible_at="not_applicable",
            allowed_universe=("510300.SH",),
            license_class="approved-research",
            egress_class=EgressClass.LOCAL_ONLY,
        )
    )


def _tool() -> ModelToolSpec:
    return ModelToolSpec(
        kind=ModelToolKind.FUNCTION,
        name="author_save_strategy_draft",
        description="Save one already validated strategy draft.",
        input_schema={
            "type": "object",
            "properties": {
                "strategy_id": {"type": "string"},
                "candidate_hash": {"type": "string"},
            },
            "required": ["strategy_id", "candidate_hash"],
            "additionalProperties": False,
        },
        requires_approval=True,
    )


def _request(run_id: str = "run-r52") -> ModelRequest:
    return ModelRequest(
        run_id=run_id,
        agent_name="author-copilot",
        instructions="Use only the registered authoring tools.",
        input_text="Save the validated draft.",
        max_turns=4,
        max_output_tokens=256,
        tools=(_tool(),),
    )


def _interrupted(*, call_ids: tuple[str, ...] = ("call-write-1",)) -> ModelResult:
    interruptions = tuple(
        ModelInterruption(
            call_id=call_id,
            tool_name="author_save_strategy_draft",
            arguments={
                "strategy_id": f"strategy-{index}",
                "candidate_hash": chr(96 + index) * 64,
            },
        )
        for index, call_id in enumerate(call_ids, start=1)
    )
    return ModelResult(
        final_output=None,
        tool_calls=(),
        usage=ModelUsage(requests=1, input_tokens=30, output_tokens=5),
        interruptions=interruptions,
        continuation=ModelContinuation(
            provider="scripted",
            payload={
                "run_id": "run-r52",
                "pending_call_ids": list(call_ids),
            },
        ),
    )


def _terminal() -> ModelResult:
    return ModelResult(
        final_output={"claims": [], "uncertainty": None},
        tool_calls=(),
        usage=ModelUsage(requests=1, input_tokens=20, output_tokens=10),
        interruptions=(),
        continuation=None,
    )


def _store(
    tmp_path: Path,
) -> tuple[AgentDatabase, AgentStoreReader, AgentStoreWriter]:
    database = AgentDatabase(tmp_path)
    database.initialize()
    reader = AgentStoreReader(database)
    writer = AgentStoreWriter(database)
    manifest = AgentManifest(
        manifest_id="manifest-r52",
        agent_version="r5.2.0",
        prompt_version="author-v1",
        prompt_hash=HASH_B,
        tool_schema_version="author-tools-v1",
        tool_schema_hash=canonical_sha256((_tool(),)),
        model_profile=ModelProfile.BALANCED,
        model_snapshot="scripted-v1",
    )
    writer.put_manifest(manifest)
    writer.create_session(
        AgentSession(
            session_id="session-r52",
            created_at=NOW,
            retention_class=RetentionClass.AUDIT,
        )
    )
    writer.create_run(
        AgentRun(
            run_id="run-r52",
            session_id="session-r52",
            status=RunStatus.QUEUED,
            objective="Save the validated draft.",
            authority_hash=HASH_A,
            max_model_tokens=512,
            max_model_spend_usd=Decimal("0.20"),
            model_profile=ModelProfile.BALANCED,
            manifest_hash=manifest.manifest_hash,
            created_at=NOW,
        )
    )
    writer.transition_run(
        run_id="run-r52",
        expected_revision=0,
        target=RunStatus.RUNNING,
        occurred_at=NOW,
        event_type="run_started",
        event_payload_hash=canonical_sha256({"run_id": "run-r52"}),
    )
    return database, reader, writer


def _runtime(
    tmp_path: Path,
    *,
    result: ModelResult | None = None,
) -> tuple[
    AgentApprovalRuntime,
    AgentDatabase,
    AgentStoreReader,
    AgentStoreWriter,
    ScriptedAgentModel,
    _ActionResolver,
    _Clock,
]:
    database, reader, writer = _store(tmp_path)
    model = ScriptedAgentModel(script=(ScriptedOutcome(result=result or _terminal()),))
    resolver = _ActionResolver()
    clock = _Clock()
    request = _request()
    runtime = AgentApprovalRuntime(
        reader=reader,
        writer=writer,
        model=model,
        request_resolver=lambda run_id: request if run_id == request.run_id else None,
        action_resolver=resolver,
        clock=clock,
        settings=ApprovalRuntimeSettings(
            approval_ttl=timedelta(minutes=15),
            resume_lease_ttl=timedelta(minutes=2),
        ),
    )
    return runtime, database, reader, writer, model, resolver, clock


@pytest.mark.asyncio
@pytest.mark.parametrize("approved", [True, False])
async def test_approve_and_reject_resume_only_the_same_run(
    tmp_path: Path,
    approved: bool,
) -> None:
    runtime, database, reader, _writer, model, _resolver, _clock = _runtime(tmp_path)
    batch = runtime.suspend(request=_request(), result=_interrupted())
    approval = batch.approvals[0]

    outcome = await runtime.decide_and_resume(
        request_id=approval.request_id,
        expected_action_hash=approval.action_hash,
        approved=approved,
        operator_id="operator-r52",
        reason="Reviewed the exact immutable action.",
    )

    assert outcome.resumed is True
    assert outcome.approval.status is (
        ApprovalStatus.APPROVED if approved else ApprovalStatus.REJECTED
    )
    stored_run = reader.get_run("run-r52")
    assert stored_run is not None
    assert stored_run.status is RunStatus.COMPLETED
    assert reader.get_continuation("run-r52") is None
    resume = cast(ResumeModelRequest, model.requests[-1])
    assert resume.request.run_id == "run-r52"
    assert resume.continuation.provider == "scripted"
    assert resume.decisions[0].approved is approved
    assert resume.decisions[0].call_id == "call-write-1"
    assert verify_audit_chain(database.get_connection()).event_count > 0


@pytest.mark.asyncio
@pytest.mark.parametrize("drift", ["authority", "snapshot", "budget"])
async def test_current_authority_snapshot_and_budget_are_recomputed_before_resume(
    tmp_path: Path,
    drift: str,
) -> None:
    runtime, _database, reader, _writer, model, resolver, _clock = _runtime(tmp_path)
    batch = runtime.suspend(request=_request(), result=_interrupted())
    approval = batch.approvals[0]
    if drift == "authority":
        resolver.authority_hash = HASH_B
    elif drift == "snapshot":
        resolver.context = _context(snapshot="snapshot-drifted")
    else:
        resolver.budget = replace(resolver.budget, max_output_bytes=32_768)

    with pytest.raises(ApprovalRuntimeViolation, match="action"):
        await runtime.decide_and_resume(
            request_id=approval.request_id,
            expected_action_hash=approval.action_hash,
            approved=True,
            operator_id="operator-r52",
            reason=None,
        )

    stored_run = reader.get_run("run-r52")
    assert stored_run is not None
    assert stored_run.status is RunStatus.WAITING_APPROVAL
    stored_approval = reader.get_approval(approval.request_id)
    assert stored_approval is not None
    assert stored_approval.status is ApprovalStatus.PENDING
    assert not model.requests


@pytest.mark.asyncio
async def test_expired_or_hash_tampered_approval_fails_closed(
    tmp_path: Path,
) -> None:
    runtime, _database, reader, _writer, model, _resolver, clock = _runtime(tmp_path)
    batch = runtime.suspend(request=_request(), result=_interrupted())
    approval = batch.approvals[0]

    with pytest.raises(AgentConflictError, match="hash"):
        await runtime.decide_and_resume(
            request_id=approval.request_id,
            expected_action_hash=HASH_B,
            approved=True,
            operator_id="operator-r52",
            reason=None,
        )

    clock.current = NOW + timedelta(minutes=15)
    with pytest.raises(AgentConflictError, match="expired"):
        await runtime.decide_and_resume(
            request_id=approval.request_id,
            expected_action_hash=approval.action_hash,
            approved=True,
            operator_id="operator-r52",
            reason=None,
        )

    stored = reader.get_approval(approval.request_id)
    assert stored is not None
    assert stored.status is ApprovalStatus.PENDING
    assert not model.requests


@pytest.mark.asyncio
@pytest.mark.parametrize("target", ["action", "continuation", "arguments"])
async def test_persisted_action_continuation_and_arguments_tamper_is_detected(
    tmp_path: Path,
    target: str,
) -> None:
    runtime, database, _reader, _writer, model, _resolver, _clock = _runtime(tmp_path)
    batch = runtime.suspend(request=_request(), result=_interrupted())
    approval = batch.approvals[0]
    connection = database.get_connection()
    if target == "action":
        connection.execute(
            "UPDATE agent_approvals SET action_payload=? WHERE request_id=?",
            (b'{"tampered":true}', approval.request_id),
        )
    else:
        row = connection.execute(
            "SELECT payload_json FROM agent_run_continuations WHERE run_id=?",
            ("run-r52",),
        ).fetchone()
        payload = orjson.loads(bytes(row[0]))
        if target == "continuation":
            payload["continuation"]["payload"]["run_id"] = "run-other"
            replacement = canonical_bytes(payload)
            connection.execute(
                "UPDATE agent_run_continuations SET payload_json=? WHERE run_id=?",
                (replacement, "run-r52"),
            )
        else:
            payload["interruptions"][0]["arguments_hash"] = HASH_B
            replacement = canonical_bytes(payload)
            connection.execute(
                """
                UPDATE agent_run_continuations
                SET payload_json=?, payload_hash=? WHERE run_id=?
                """,
                (replacement, canonical_sha256(payload), "run-r52"),
            )
    connection.commit()

    with pytest.raises(ApprovalRuntimeViolation):
        await runtime.decide_and_resume(
            request_id=approval.request_id,
            expected_action_hash=approval.action_hash,
            approved=True,
            operator_id="operator-r52",
            reason=None,
        )
    assert not model.requests


def test_concurrent_decisions_for_one_batch_resume_exactly_once(
    tmp_path: Path,
) -> None:
    runtime, _database, reader, _writer, model, _resolver, _clock = _runtime(tmp_path)
    batch = runtime.suspend(
        request=_request(),
        result=_interrupted(call_ids=("call-write-1", "call-write-2")),
    )

    def decide(index: int) -> bool:
        approval = batch.approvals[index]
        result = asyncio.run(
            runtime.decide_and_resume(
                request_id=approval.request_id,
                expected_action_hash=approval.action_hash,
                approved=True,
                operator_id=f"operator-{index}",
                reason="Reviewed batch action.",
            )
        )
        return result.resumed

    with ThreadPoolExecutor(max_workers=2) as pool:
        resumed = tuple(pool.map(decide, (0, 1)))

    assert sum(resumed) == 1
    assert sum(isinstance(item, ResumeModelRequest) for item in model.requests) == 1
    stored_run = reader.get_run("run-r52")
    assert stored_run is not None
    assert stored_run.status is RunStatus.COMPLETED


@pytest.mark.asyncio
async def test_restart_reconstructs_persisted_state_and_resumes(
    tmp_path: Path,
) -> None:
    runtime, _database, reader, writer, _model, resolver, clock = _runtime(tmp_path)
    batch = runtime.suspend(request=_request(), result=_interrupted())
    approval = batch.approvals[0]
    restarted_model = ScriptedAgentModel(script=(ScriptedOutcome(result=_terminal()),))
    restarted = AgentApprovalRuntime(
        reader=reader,
        writer=writer,
        model=restarted_model,
        request_resolver=_request,
        action_resolver=resolver,
        clock=clock,
        settings=ApprovalRuntimeSettings(
            approval_ttl=timedelta(minutes=15),
            resume_lease_ttl=timedelta(minutes=2),
        ),
    )

    outcome = await restarted.decide_and_resume(
        request_id=approval.request_id,
        expected_action_hash=approval.action_hash,
        approved=True,
        operator_id="operator-restarted",
        reason="Resume after restart.",
    )

    assert outcome.resumed is True
    assert len(restarted_model.requests) == 1
    stored_run = reader.get_run("run-r52")
    assert stored_run is not None
    assert stored_run.status is RunStatus.COMPLETED


@pytest.mark.asyncio
async def test_changed_model_request_cannot_resume_old_provider_state(
    tmp_path: Path,
) -> None:
    runtime, _database, reader, writer, model, resolver, clock = _runtime(tmp_path)
    batch = runtime.suspend(request=_request(), result=_interrupted())
    approval = batch.approvals[0]
    changed = replace(_request(), max_output_tokens=128)
    restarted = AgentApprovalRuntime(
        reader=reader,
        writer=writer,
        model=model,
        request_resolver=lambda _run_id: changed,
        action_resolver=resolver,
        clock=clock,
        settings=ApprovalRuntimeSettings(
            approval_ttl=timedelta(minutes=15),
            resume_lease_ttl=timedelta(minutes=2),
        ),
    )

    with pytest.raises(ApprovalRuntimeConflict, match="request"):
        await restarted.decide_and_resume(
            request_id=approval.request_id,
            expected_action_hash=approval.action_hash,
            approved=True,
            operator_id="operator-r52",
            reason=None,
        )
    assert not model.requests


@pytest.mark.asyncio
async def test_provider_timeout_pauses_and_restart_retry_uses_same_continuation(
    tmp_path: Path,
) -> None:
    runtime, _database, reader, writer, _model, resolver, clock = _runtime(tmp_path)
    timeout_model = ScriptedAgentModel(
        script=(
            ScriptedFailure(
                kind=ModelFailureKind.TIMEOUT,
                message="provider timed out",
            ),
        )
    )
    runtime = AgentApprovalRuntime(
        reader=reader,
        writer=writer,
        model=timeout_model,
        request_resolver=_request,
        action_resolver=resolver,
        clock=clock,
        settings=ApprovalRuntimeSettings(
            approval_ttl=timedelta(minutes=15),
            resume_lease_ttl=timedelta(minutes=2),
        ),
    )
    batch = runtime.suspend(request=_request(), result=_interrupted())
    approval = batch.approvals[0]

    with pytest.raises(ApprovalRuntimeUnavailable, match="provider"):
        await runtime.decide_and_resume(
            request_id=approval.request_id,
            expected_action_hash=approval.action_hash,
            approved=True,
            operator_id="operator-r52",
            reason=None,
        )

    paused = reader.get_run("run-r52")
    assert paused is not None
    assert paused.status is RunStatus.PAUSED
    assert reader.get_continuation("run-r52") is not None
    restarted = AgentApprovalRuntime(
        reader=reader,
        writer=writer,
        model=ScriptedAgentModel(script=(ScriptedOutcome(result=_terminal()),)),
        request_resolver=_request,
        action_resolver=resolver,
        clock=clock,
        settings=ApprovalRuntimeSettings(
            approval_ttl=timedelta(minutes=15),
            resume_lease_ttl=timedelta(minutes=2),
        ),
    )
    assert await restarted.resume_ready("run-r52") is True
    completed = reader.get_run("run-r52")
    assert completed is not None
    assert completed.status is RunStatus.COMPLETED


@pytest.mark.asyncio
async def test_runtime_timeout_precedes_lease_expiry_and_pauses(
    tmp_path: Path,
) -> None:
    _runtime_value, _database, reader, writer, _model, resolver, clock = _runtime(
        tmp_path
    )
    runtime = AgentApprovalRuntime(
        reader=reader,
        writer=writer,
        model=_HangingModel(),
        request_resolver=_request,
        action_resolver=resolver,
        clock=clock,
        settings=ApprovalRuntimeSettings(
            approval_ttl=timedelta(minutes=15),
            resume_lease_ttl=timedelta(minutes=2),
            provider_timeout=timedelta(milliseconds=5),
        ),
    )
    batch = runtime.suspend(request=_request(), result=_interrupted())
    approval = batch.approvals[0]

    with pytest.raises(ApprovalRuntimeUnavailable, match="provider"):
        await asyncio.wait_for(
            runtime.decide_and_resume(
                request_id=approval.request_id,
                expected_action_hash=approval.action_hash,
                approved=True,
                operator_id="operator-timeout",
                reason=None,
            ),
            timeout=0.25,
        )

    paused = reader.get_run("run-r52")
    assert paused is not None
    assert paused.status is RunStatus.PAUSED
    assert reader.get_continuation("run-r52") is not None


def test_sensitive_provider_continuation_is_never_persisted(tmp_path: Path) -> None:
    runtime, _database, reader, _writer, model, _resolver, _clock = _runtime(tmp_path)
    unsafe = replace(
        _interrupted(),
        continuation=ModelContinuation(
            provider="scripted",
            payload={"api_key": "must-not-be-persisted"},
        ),
    )

    with pytest.raises(ApprovalRuntimeViolation, match="sensitive"):
        runtime.suspend(request=_request(), result=unsafe)

    assert reader.get_continuation("run-r52") is None
    assert reader.list_run_approvals("run-r52") == ()
    assert not model.requests


def test_suspension_storage_unavailable_uses_runtime_failure_boundary(
    tmp_path: Path,
) -> None:
    runtime, database, _reader, _writer, model, _resolver, _clock = _runtime(tmp_path)
    database.close_all()

    with pytest.raises(ApprovalRuntimeUnavailable, match="storage"):
        runtime.suspend(request=_request(), result=_interrupted())

    assert not model.requests


@pytest.mark.asyncio
async def test_storage_unavailable_never_calls_provider(tmp_path: Path) -> None:
    runtime, database, _reader, _writer, model, _resolver, _clock = _runtime(tmp_path)
    batch = runtime.suspend(request=_request(), result=_interrupted())
    approval = batch.approvals[0]
    database.close_all()

    with pytest.raises(AgentPersistenceError):
        await runtime.decide_and_resume(
            request_id=approval.request_id,
            expected_action_hash=approval.action_hash,
            approved=True,
            operator_id="operator-r52",
            reason=None,
        )
    assert not model.requests
