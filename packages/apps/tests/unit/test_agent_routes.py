"""R5.1 Agent HTTP contract and thin route behavior."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from ditto_agent.contracts.runtime import ModelProfile, RetentionClass, RunStatus
from ditto_agent.runtime.service import (
    AgentApprovalDecision,
    AgentApprovalDecisionCommand,
    AgentEventView,
    AgentRequestConflict,
    AgentRunCancelCommand,
    AgentRunCreateCommand,
    AgentRuntimePort,
    AgentRuntimeUnavailable,
    AgentRunView,
    AgentSessionCreateCommand,
    AgentSessionView,
)
from ditto_apps.api.errors import APIError
from ditto_apps.api.routes.agent_routes import (
    cancel_agent_run,
    create_agent_run,
    create_agent_session,
)
from ditto_apps.models.agent import (
    AgentRunCancelRequest,
    AgentRunCreateRequest,
    AgentSessionCreateRequest,
)
from ditto_apps.openapi_contract import create_openapi_app

_NOW = datetime(2026, 8, 16, 3, 0, tzinfo=UTC)
_HASH = "a" * 64

_create_agent_session = getattr(
    create_agent_session, "__dishka_orig_func__", create_agent_session
)
_create_agent_run = getattr(create_agent_run, "__dishka_orig_func__", create_agent_run)
_cancel_agent_run = getattr(cancel_agent_run, "__dishka_orig_func__", cancel_agent_run)


class _RecordingRuntime(AgentRuntimePort):
    def __init__(self) -> None:
        self.commands: list[object] = []

    def create_session(self, command: AgentSessionCreateCommand) -> AgentSessionView:
        self.commands.append(command)
        return AgentSessionView(
            session_id="session-1",
            created_at=_NOW,
            retention_class=command.retention_class,
        )

    def create_run(self, command: AgentRunCreateCommand) -> AgentRunView:
        self.commands.append(command)
        return _run_view()

    def get_run(self, run_id: str) -> AgentRunView:
        self.commands.append(run_id)
        return _run_view()

    def list_run_events(
        self, run_id: str, *, after_event_id: int | None = None
    ) -> tuple[AgentEventView, ...]:
        self.commands.append((run_id, after_event_id))
        return ()

    def cancel_run(self, command: AgentRunCancelCommand) -> AgentRunView:
        self.commands.append(command)
        return _run_view(status=RunStatus.CANCELLED, revision=2)

    def decide_approval(
        self, command: AgentApprovalDecisionCommand
    ) -> AgentApprovalDecision:
        self.commands.append(command)
        raise NotImplementedError


def _run_view(
    *,
    status: RunStatus = RunStatus.QUEUED,
    revision: int = 0,
) -> AgentRunView:
    return AgentRunView(
        run_id="run-1",
        session_id="session-1",
        status=status,
        objective_hash=_HASH,
        authority_hash=_HASH,
        max_model_tokens=512,
        max_model_spend_usd=Decimal("0.25"),
        model_profile=ModelProfile.BALANCED,
        manifest_hash=_HASH,
        created_at=_NOW,
        started_at=None,
        finished_at=_NOW if status is RunStatus.CANCELLED else None,
        revision=revision,
    )


def test_openapi_registers_stable_r51_agent_surface() -> None:
    schema = create_openapi_app().openapi()

    assert {
        "/api/v1/agent/sessions",
        "/api/v1/agent/runs",
        "/api/v1/agent/runs/{run_id}",
        "/api/v1/agent/runs/{run_id}/events",
        "/api/v1/agent/runs/{run_id}/cancel",
        "/api/v1/agent/approvals/{approval_id}/decision",
    } <= schema["paths"].keys()
    assert schema["paths"]["/api/v1/agent/sessions"]["post"]["operationId"] == (
        "agent_create_agent_session"
    )
    parameters = schema["paths"]["/api/v1/agent/runs"]["post"]["parameters"]
    assert any(
        item["name"] == "Idempotency-Key" and item["required"] is True
        for item in parameters
    )


def test_openapi_registers_fixed_campaign_surface_and_write_fences() -> None:
    schema = create_openapi_app().openapi()
    campaign_paths = {
        "/api/v1/agent/campaigns",
        "/api/v1/agent/campaigns/{campaign_id}/approve",
        "/api/v1/agent/campaigns/{campaign_id}",
        "/api/v1/agent/campaigns/{campaign_id}/events",
        "/api/v1/agent/campaigns/{campaign_id}/cancel",
    }

    assert campaign_paths <= schema["paths"].keys()
    assert all("patch" not in schema["paths"][path] for path in campaign_paths)
    for path in (
        "/api/v1/agent/campaigns",
        "/api/v1/agent/campaigns/{campaign_id}/approve",
        "/api/v1/agent/campaigns/{campaign_id}/cancel",
    ):
        parameters = schema["paths"][path]["post"]["parameters"]
        assert any(
            item["name"] == "Idempotency-Key" and item["required"] is True
            for item in parameters
        )

    create_schema = schema["components"]["schemas"]["AgentCampaignCreateRequest"]
    approve_schema = schema["components"]["schemas"]["AgentCampaignApproveRequest"]
    cancel_schema = schema["components"]["schemas"]["AgentCampaignCancelRequest"]
    assert create_schema["additionalProperties"] is False
    assert approve_schema["additionalProperties"] is False
    assert cancel_schema["additionalProperties"] is False


@pytest.mark.asyncio
async def test_create_routes_translate_dtos_to_runtime_commands() -> None:
    runtime = _RecordingRuntime()

    session = await _create_agent_session(
        AgentSessionCreateRequest(retention_class="audit"),
        runtime,
        "session-key",
    )
    run = await _create_agent_run(
        AgentRunCreateRequest(
            session_id="session-1",
            objective="Explain the frozen evidence.",
            authority_hash=_HASH,
            max_model_tokens=512,
            max_model_spend_usd=Decimal("0.25"),
            model_profile="balanced",
        ),
        runtime,
        "run-key",
    )

    assert session.data.session_id == "session-1"
    assert run.data.run_id == "run-1"
    assert runtime.commands == [
        AgentSessionCreateCommand(
            retention_class=RetentionClass.AUDIT,
            idempotency_key="session-key",
        ),
        AgentRunCreateCommand(
            session_id="session-1",
            objective="Explain the frozen evidence.",
            authority_hash=_HASH,
            max_model_tokens=512,
            max_model_spend_usd=Decimal("0.25"),
            model_profile=ModelProfile.BALANCED,
            idempotency_key="run-key",
        ),
    ]


@pytest.mark.asyncio
async def test_cancel_route_preserves_revision_fence() -> None:
    runtime = _RecordingRuntime()

    response = await _cancel_agent_run(
        "run-1",
        AgentRunCancelRequest(expected_revision=1),
        runtime,
    )

    assert response.data.status is RunStatus.CANCELLED
    assert runtime.commands == [
        AgentRunCancelCommand(run_id="run-1", expected_revision=1)
    ]


@pytest.mark.asyncio
async def test_idempotency_conflict_and_disabled_runtime_are_structured() -> None:
    class ConflictRuntime(_RecordingRuntime):
        def create_session(
            self, command: AgentSessionCreateCommand
        ) -> AgentSessionView:
            raise AgentRequestConflict(
                "different request body", reason_code="agent_idempotency_hash_conflict"
            )

    with pytest.raises(APIError) as conflict:
        await _create_agent_session(
            AgentSessionCreateRequest(), ConflictRuntime(), "same-key"
        )
    assert conflict.value.status_code == 409
    assert conflict.value.error_code == "AGENT_IDEMPOTENCY_HASH_CONFLICT"

    class DisabledRuntime(_RecordingRuntime):
        def create_run(self, command: AgentRunCreateCommand) -> AgentRunView:
            raise AgentRuntimeUnavailable("agent_feature_disabled")

    with pytest.raises(APIError) as unavailable:
        await _create_agent_run(
            AgentRunCreateRequest(
                session_id="session-1",
                objective="Explain evidence.",
                authority_hash=_HASH,
            ),
            DisabledRuntime(),
            "run-key",
        )
    assert unavailable.value.status_code == 503
    assert unavailable.value.error_code == "AGENT_UNAVAILABLE"
