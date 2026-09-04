from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from ditto_agent.contracts.approval import ActionBudget, ApprovalAction, ApprovalRequest
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
from ditto_agent.storage.sqlite.database import AgentDatabase
from ditto_agent.storage.sqlite.errors import (
    AgentConflictError,
    IdempotencyConflictError,
)
from ditto_agent.storage.sqlite.reader import AgentStoreReader
from ditto_agent.storage.sqlite.records import (
    ApprovalStatus,
    IdempotencyDisposition,
    IdempotencyStatus,
    RetentionMetadata,
)
from ditto_agent.storage.sqlite.writer import AgentStoreWriter

NOW = datetime(2026, 8, 16, 2, 0, tzinfo=UTC)


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _manifest() -> AgentManifest:
    return AgentManifest(
        manifest_id="manifest-001",
        agent_version="r5.0",
        prompt_version="prompt-v1",
        prompt_hash=_hash("prompt"),
        tool_schema_version="tools-v1",
        tool_schema_hash=_hash("tools"),
        model_profile=ModelProfile.BALANCED,
        model_snapshot="stub-model",
    )


def _run(manifest: AgentManifest) -> AgentRun:
    return AgentRun(
        run_id="run-001",
        session_id="session-001",
        status=RunStatus.QUEUED,
        objective="Summarize governed evidence without retaining the raw prompt.",
        authority_hash=_hash("authority"),
        max_model_tokens=4_096,
        max_model_spend_usd=Decimal("0.25"),
        model_profile=ModelProfile.BALANCED,
        manifest_hash=manifest.manifest_hash,
        created_at=NOW,
    )


def _approval() -> ApprovalRequest:
    context = TemporalToolContext.from_host(
        TemporalContextInput(
            decision_time=NOW,
            knowledge_cutoff=NOW - timedelta(minutes=1),
            publication_cutoff=NOW - timedelta(minutes=2),
            source_snapshot_id="snapshot-001",
            execution_eligible_at="not_applicable",
            allowed_universe=("510300.SH",),
            license_class="internal",
            egress_class=EgressClass.LOCAL_ONLY,
        )
    )
    return ApprovalRequest.issue(
        request_id="approval-001",
        run_id="run-001",
        action=ApprovalAction(
            action_kind="save_draft",
            tool_name="save_strategy_draft",
            parameters={"draft_hash": _hash("draft")},
            subject_identity="strategy-draft-001",
            required_authority="research_author",
            authority_hash=_hash("authority"),
            temporal_context=context,
            budget=ActionBudget(
                max_tool_calls=1,
                max_output_bytes=4_096,
                max_model_tokens=1_024,
                max_model_spend_usd=Decimal("0.05"),
            ),
            expires_at=NOW + timedelta(minutes=10),
        ),
    )


def _store(tmp_path: Path) -> tuple[AgentStoreWriter, AgentStoreReader]:
    database = AgentDatabase(tmp_path)
    database.initialize()
    return AgentStoreWriter(database), AgentStoreReader(database)


def test_put_manifest_accepts_exact_replay_on_runtime_restart(tmp_path: Path) -> None:
    writer, _ = _store(tmp_path)
    manifest = _manifest()

    writer.put_manifest(manifest)
    writer.put_manifest(manifest)


def test_store_persists_run_events_approval_and_retention_without_raw_objective(
    tmp_path: Path,
) -> None:
    writer, reader = _store(tmp_path)
    manifest = _manifest()
    session = AgentSession(
        session_id="session-001",
        created_at=NOW,
        retention_class=RetentionClass.STANDARD,
    )
    writer.put_manifest(manifest)
    writer.create_session(session)
    stored_run = writer.create_run(_run(manifest))

    assert reader.get_session(session.session_id) == session
    assert stored_run.objective_hash == _hash(
        "Summarize governed evidence without retaining the raw prompt."
    )
    assert not hasattr(stored_run, "objective")

    first = writer.append_run_event(
        run_id=stored_run.run_id,
        event_type="run_queued",
        payload_hash=_hash("queued"),
        occurred_at=NOW,
    )
    second = writer.append_run_event(
        run_id=stored_run.run_id,
        event_type="model_started",
        payload_hash=_hash("model"),
        occurred_at=NOW + timedelta(seconds=1),
    )
    assert first.run_sequence == 1
    assert second.prev_hash == first.event_hash
    assert reader.list_run_events(stored_run.run_id) == (first, second)

    running = writer.transition_run(
        run_id=stored_run.run_id,
        expected_revision=0,
        target=RunStatus.RUNNING,
        occurred_at=NOW + timedelta(seconds=2),
    )
    assert running.status is RunStatus.RUNNING
    assert running.revision == 1
    with pytest.raises(AgentConflictError):
        writer.transition_run(
            run_id=stored_run.run_id,
            expected_revision=0,
            target=RunStatus.COMPLETED,
            occurred_at=NOW + timedelta(seconds=3),
        )

    approval = _approval()
    writer.create_approval(approval, requested_at=NOW)
    decision = writer.decide_approval(
        request_id=approval.request_id,
        expected_action_hash=approval.action_hash,
        approved=True,
        operator_id="operator-001",
        reason="Reviewed exact action hash.",
        decided_at=NOW + timedelta(minutes=1),
    )
    assert decision.status is ApprovalStatus.APPROVED
    assert reader.get_approval(approval.request_id) == decision

    retention = RetentionMetadata(
        target_kind="session",
        target_id=session.session_id,
        retention_class=RetentionClass.STANDARD,
        retain_until=NOW + timedelta(days=30),
        legal_hold=False,
        updated_at=NOW,
    )
    writer.set_retention(retention)
    assert reader.get_retention("session", session.session_id) == retention


def test_idempotency_replays_same_body_and_conflicts_on_drift(tmp_path: Path) -> None:
    writer, _reader = _store(tmp_path)
    request_hash = _hash("request-body")

    created = writer.reserve_idempotency(
        scope="create_session",
        idempotency_key="idem-001",
        request_hash=request_hash,
        occurred_at=NOW,
    )
    replay = writer.reserve_idempotency(
        scope="create_session",
        idempotency_key="idem-001",
        request_hash=request_hash,
        occurred_at=NOW + timedelta(seconds=1),
    )

    assert created.disposition is IdempotencyDisposition.CREATED
    assert replay.disposition is IdempotencyDisposition.REPLAY
    assert replay.record.status is IdempotencyStatus.PENDING

    completed = writer.complete_idempotency(
        scope="create_session",
        idempotency_key="idem-001",
        expected_request_hash=request_hash,
        result_identity="session-001",
        occurred_at=NOW + timedelta(seconds=2),
    )
    assert completed.status is IdempotencyStatus.COMPLETED

    with pytest.raises(IdempotencyConflictError):
        writer.reserve_idempotency(
            scope="create_session",
            idempotency_key="idem-001",
            request_hash=_hash("different-body"),
            occurred_at=NOW + timedelta(seconds=3),
        )
