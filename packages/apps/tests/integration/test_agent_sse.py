"""Persisted Agent SSE resume and cancellation integration contracts."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import orjson
import pytest
from dishka import AsyncContainer, Provider, Scope, make_async_container, provide
from dishka.integrations.fastapi import setup_dishka
from ditto_agent._canonical import canonical_sha256
from ditto_agent.contracts.runtime import (
    AgentManifest,
    ModelProfile,
    RetentionClass,
    RunStatus,
)
from ditto_agent.runtime.service import (
    AgentInvalidRequest,
    AgentRequestConflict,
    AgentResourceNotFound,
    AgentRunCancelCommand,
    AgentRunCreateCommand,
    AgentRuntimePort,
    AgentRuntimeUnavailable,
    AgentSessionCreateCommand,
)
from ditto_apps.api.errors import APIError
from ditto_apps.api.routes.agent_routes import encode_agent_sse, router
from ditto_apps.middleware import api_error_handler
from ditto_apps.registry.agent.database_provider import (
    AgentDatabaseBundle,
    build_agent_database,
)
from ditto_apps.registry.agent.provider import AgentRuntimeProvider
from ditto_apps.registry.agent.runtime import PersistedAgentRuntime
from ditto_apps.registry.agent.settings import AgentFeatureSettings
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

_NOW = datetime(2026, 8, 16, 4, 0, tzinfo=UTC)
_HASH = "b" * 64


def _manifest() -> AgentManifest:
    return AgentManifest(
        manifest_id="r5.1-balanced",
        agent_version="r5.1",
        prompt_version="evidence-v1",
        prompt_hash="1" * 64,
        tool_schema_version="read-evidence-v1",
        tool_schema_hash="2" * 64,
        model_profile=ModelProfile.BALANCED,
        model_snapshot="fake-r5.1",
    )


def _runtime(tmp_path: Path) -> tuple[PersistedAgentRuntime, AgentDatabaseBundle]:
    bundle = build_agent_database(tmp_path)
    manifest = _manifest()
    bundle.writer.put_manifest(manifest)
    runtime = PersistedAgentRuntime(
        reader=bundle.reader,
        writer=bundle.writer,
        manifest=manifest,
        clock=lambda: _NOW,
    )
    return runtime, bundle


def _http_app(runtime: AgentRuntimePort) -> tuple[FastAPI, AsyncContainer]:
    class TestProvider(Provider):
        scope = Scope.APP

        @provide
        def agent_runtime(self) -> AgentRuntimePort:
            return runtime

    container = make_async_container(TestProvider())
    app = FastAPI()
    setup_dishka(container=container, app=app)
    app.include_router(router, prefix="/api/v1")
    app.add_exception_handler(APIError, api_error_handler)
    return app, container


def test_persisted_sse_is_monotonic_and_last_event_id_resumes_without_execution(
    tmp_path: Path,
) -> None:
    runtime, bundle = _runtime(tmp_path)
    try:
        session = runtime.create_session(
            AgentSessionCreateCommand(
                retention_class=RetentionClass.STANDARD,
                idempotency_key="session-sse",
            )
        )
        run = runtime.create_run(
            AgentRunCreateCommand(
                session_id=session.session_id,
                objective="Explain evidence.",
                authority_hash=_HASH,
                max_model_tokens=512,
                max_model_spend_usd=Decimal("0.25"),
                model_profile=ModelProfile.BALANCED,
                idempotency_key="run-sse",
            )
        )
        second = bundle.writer.append_run_event(
            run_id=run.run_id,
            event_type="provider_attempt",
            payload_hash=canonical_sha256({"attempt": 1}),
            occurred_at=_NOW + timedelta(seconds=1),
        )
        third = bundle.writer.append_run_event(
            run_id=run.run_id,
            event_type="run_completed",
            payload_hash=canonical_sha256({"status": "completed"}),
            occurred_at=_NOW + timedelta(seconds=2),
        )

        all_events = runtime.list_run_events(run.run_id)
        resumed = runtime.list_run_events(
            run.run_id, after_event_id=all_events[0].event_id
        )
        payload = encode_agent_sse(resumed)

        assert tuple(event.event_id for event in all_events) == tuple(
            sorted(event.event_id for event in all_events)
        )
        assert tuple(event.event_id for event in resumed) == (
            second.event_id,
            third.event_id,
        )
        assert payload.count(b"event: provider_attempt\n") == 1
        assert payload.count(b"event: run_completed\n") == 1
        assert f"id: {all_events[0].event_id}\n".encode() not in payload
        data_lines = [
            line.removeprefix(b"data: ")
            for line in payload.splitlines()
            if line.startswith(b"data: ")
        ]
        decoded = [orjson.loads(line) for line in data_lines]
        assert [item["schema_version"] for item in decoded] == [1, 1]
        assert [item["payload_hash"] for item in decoded] == [
            second.payload_hash,
            third.payload_hash,
        ]
        assert len(bundle.reader.list_run_events(run.run_id)) == 3
    finally:
        bundle.close()


@pytest.mark.asyncio
async def test_http_sse_honors_last_event_id_and_remains_read_only(
    tmp_path: Path,
) -> None:
    runtime, bundle = _runtime(tmp_path)
    app, container = _http_app(runtime)
    try:
        session = runtime.create_session(
            AgentSessionCreateCommand(
                retention_class=RetentionClass.STANDARD,
                idempotency_key="http-sse-session",
            )
        )
        run = runtime.create_run(
            AgentRunCreateCommand(
                session_id=session.session_id,
                objective="Replay persisted evidence.",
                authority_hash=_HASH,
                max_model_tokens=512,
                max_model_spend_usd=Decimal("0.25"),
                model_profile=ModelProfile.BALANCED,
                idempotency_key="http-sse-run",
            )
        )
        first = runtime.list_run_events(run.run_id)[0]
        second = bundle.writer.append_run_event(
            run_id=run.run_id,
            event_type="provider_attempt",
            payload_hash=canonical_sha256({"attempt": 1}),
            occurred_at=_NOW + timedelta(seconds=1),
        )

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            response = await client.get(
                f"/api/v1/agent/runs/{run.run_id}/events",
                headers={"Last-Event-ID": str(first.event_id)},
            )

        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        assert f"id: {first.event_id}\n" not in response.text
        assert f"id: {second.event_id}\n" in response.text
        assert len(bundle.reader.list_run_events(run.run_id)) == 2
    finally:
        await container.close()
        bundle.close()


@pytest.mark.asyncio
async def test_default_http_runtime_returns_structured_unavailable() -> None:
    provider = AgentRuntimeProvider()
    runtime = provider.runtime(AgentFeatureSettings.from_environment({}))
    app, container = _http_app(runtime)
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            response = await client.post(
                "/api/v1/agent/sessions",
                headers={"Idempotency-Key": "disabled-session"},
                json={"retention_class": "standard"},
            )

        assert response.status_code == 503
        assert response.json()["error_code"] == "AGENT_UNAVAILABLE"
    finally:
        await container.close()


@pytest.mark.asyncio
async def test_run_create_accepts_lossless_decimal_json_from_public_http_client(
    tmp_path: Path,
) -> None:
    runtime, bundle = _runtime(tmp_path)
    app, container = _http_app(runtime)
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            session_response = await client.post(
                "/api/v1/agent/sessions",
                headers={"Idempotency-Key": "http-session-create"},
                json={"retention_class": "audit"},
            )
            session_id = session_response.json()["data"]["session_id"]
            run_response = await client.post(
                "/api/v1/agent/runs",
                headers={"Idempotency-Key": "http-run-create"},
                json={
                    "session_id": session_id,
                    "objective": "Verify the public JSON request contract.",
                    "authority_hash": _HASH,
                    "max_model_tokens": 4096,
                    "max_model_spend_usd": "3.00",
                    "model_profile": "balanced",
                    "context": None,
                },
            )

        assert session_response.status_code == 201
        assert run_response.status_code == 201
        assert Decimal(run_response.json()["data"]["max_model_spend_usd"]) == Decimal(
            "3.00"
        )
        assert runtime.get_run(
            run_response.json()["data"]["run_id"]
        ).max_model_spend_usd == Decimal("3.00")
    finally:
        await container.close()
        bundle.close()


def test_same_idempotency_key_replays_exact_result_and_conflicts_on_body_drift(
    tmp_path: Path,
) -> None:
    runtime, bundle = _runtime(tmp_path)
    try:
        first = runtime.create_session(
            AgentSessionCreateCommand(
                retention_class=RetentionClass.STANDARD,
                idempotency_key="same-key",
            )
        )
        replay = runtime.create_session(
            AgentSessionCreateCommand(
                retention_class=RetentionClass.STANDARD,
                idempotency_key="same-key",
            )
        )
        assert replay == first

        with pytest.raises(AgentRequestConflict) as conflict:
            runtime.create_session(
                AgentSessionCreateCommand(
                    retention_class=RetentionClass.AUDIT,
                    idempotency_key="same-key",
                )
            )
        assert conflict.value.reason_code == "agent_idempotency_hash_conflict"
    finally:
        bundle.close()


def test_run_creation_rejects_missing_session_and_unconfigured_profile_before_write(
    tmp_path: Path,
) -> None:
    runtime, bundle = _runtime(tmp_path)
    try:
        command = AgentRunCreateCommand(
            session_id="session-missing",
            objective="Explain evidence.",
            authority_hash=_HASH,
            max_model_tokens=512,
            max_model_spend_usd=Decimal("0.25"),
            model_profile=ModelProfile.BALANCED,
            idempotency_key="missing-session-run",
        )
        with pytest.raises(AgentResourceNotFound):
            runtime.create_run(command)
        assert (
            bundle.reader.get_idempotency("agent.run.create", "missing-session-run")
            is None
        )

        session = runtime.create_session(
            AgentSessionCreateCommand(
                retention_class=RetentionClass.STANDARD,
                idempotency_key="profile-session",
            )
        )
        with pytest.raises(AgentInvalidRequest):
            runtime.create_run(
                AgentRunCreateCommand(
                    session_id=session.session_id,
                    objective="Explain evidence.",
                    authority_hash=_HASH,
                    max_model_tokens=512,
                    max_model_spend_usd=Decimal("0.25"),
                    model_profile=ModelProfile.QUALITY,
                    idempotency_key="profile-run",
                )
            )
        assert bundle.reader.get_idempotency("agent.run.create", "profile-run") is None
    finally:
        bundle.close()


def test_cancel_race_has_one_winner_and_missing_run_fails_closed(
    tmp_path: Path,
) -> None:
    runtime, bundle = _runtime(tmp_path)
    try:
        session = runtime.create_session(
            AgentSessionCreateCommand(
                retention_class=RetentionClass.EPHEMERAL,
                idempotency_key="cancel-session",
            )
        )
        run = runtime.create_run(
            AgentRunCreateCommand(
                session_id=session.session_id,
                objective="Cancel me.",
                authority_hash=_HASH,
                max_model_tokens=512,
                max_model_spend_usd=Decimal("0.25"),
                model_profile=ModelProfile.BALANCED,
                idempotency_key="cancel-run",
            )
        )

        cancelled = runtime.cancel_run(
            AgentRunCancelCommand(run_id=run.run_id, expected_revision=0)
        )
        assert cancelled.status is RunStatus.CANCELLED

        with pytest.raises(AgentRequestConflict) as race_loser:
            runtime.cancel_run(
                AgentRunCancelCommand(run_id=run.run_id, expected_revision=0)
            )
        assert race_loser.value.reason_code == "agent_run_revision_conflict"
        assert [
            event.event_type for event in runtime.list_run_events(run.run_id)
        ].count("run_cancelled") == 1

        with pytest.raises(AgentResourceNotFound):
            runtime.get_run("run-missing")
    finally:
        bundle.close()


def test_cancel_state_rolls_back_when_its_persisted_event_cannot_commit(
    tmp_path: Path,
) -> None:
    runtime, bundle = _runtime(tmp_path)
    try:
        session = runtime.create_session(
            AgentSessionCreateCommand(
                retention_class=RetentionClass.STANDARD,
                idempotency_key="atomic-cancel-session",
            )
        )
        run = runtime.create_run(
            AgentRunCreateCommand(
                session_id=session.session_id,
                objective="Keep state and event atomic.",
                authority_hash=_HASH,
                max_model_tokens=512,
                max_model_spend_usd=Decimal("0.25"),
                model_profile=ModelProfile.BALANCED,
                idempotency_key="atomic-cancel-run",
            )
        )
        connection = bundle.database.get_connection()
        connection.execute(
            """
            CREATE TEMP TRIGGER fail_cancel_event
            BEFORE INSERT ON agent_run_events
            WHEN NEW.event_type = 'run_cancelled'
            BEGIN
                SELECT RAISE(ABORT, 'injected cancel event failure');
            END
            """
        )

        with pytest.raises(AgentRuntimeUnavailable):
            runtime.cancel_run(
                AgentRunCancelCommand(run_id=run.run_id, expected_revision=0)
            )

        assert runtime.get_run(run.run_id).status is RunStatus.QUEUED
        assert [event.event_type for event in runtime.list_run_events(run.run_id)] == [
            "run_queued"
        ]
    finally:
        bundle.close()


def test_runtime_does_not_persist_raw_objective(tmp_path: Path) -> None:
    runtime, bundle = _runtime(tmp_path)
    objective = "sensitive objective must not be persisted"
    try:
        session = runtime.create_session(
            AgentSessionCreateCommand(
                retention_class=RetentionClass.STANDARD,
                idempotency_key="privacy-session",
            )
        )
        run = runtime.create_run(
            AgentRunCreateCommand(
                session_id=session.session_id,
                objective=objective,
                authority_hash=_HASH,
                max_model_tokens=512,
                max_model_spend_usd=Decimal("0.25"),
                model_profile=ModelProfile.BALANCED,
                idempotency_key="privacy-run",
            )
        )

        assert run.objective_hash == hashlib.sha256(objective.encode()).hexdigest()
        assert objective.encode() not in bundle.database.path.read_bytes()
    finally:
        bundle.close()
