"""R5.1 Agent HTTP contract and thin route behavior."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from ditto_agent.contracts.runtime import ModelProfile, RetentionClass, RunStatus
from ditto_agent.presentation import AgentContextPresentation
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
from ditto_application.queries.decision_opinion import (
    DecisionOpinionIdentity,
    DecisionOpinionReadModel,
)
from ditto_apps.api.errors import APIError
from ditto_apps.api.routes.agent_routes import (
    cancel_agent_run,
    create_agent_run,
    create_agent_session,
    get_agent_decision_opinion,
)
from ditto_apps.models.agent import (
    AgentDecisionOpinionIdentity,
    AgentDecisionOpinionQueryParams,
    AgentRunCancelRequest,
    AgentRunContext,
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
_get_agent_decision_opinion = getattr(
    get_agent_decision_opinion,
    "__dishka_orig_func__",
    get_agent_decision_opinion,
)


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
        "/api/v1/agent/capabilities",
        "/api/v1/agent/sessions",
        "/api/v1/agent/runs",
        "/api/v1/agent/runs/{run_id}",
        "/api/v1/agent/runs/{run_id}/events",
        "/api/v1/agent/runs/{run_id}/cancel",
        "/api/v1/agent/approvals",
        "/api/v1/agent/approvals/{approval_id}",
        "/api/v1/agent/approvals/{approval_id}/decision",
        "/api/v1/agent/decision-opinions",
    } <= schema["paths"].keys()
    assert schema["paths"]["/api/v1/agent/sessions"]["post"]["operationId"] == (
        "agent_create_agent_session"
    )
    parameters = schema["paths"]["/api/v1/agent/runs"]["post"]["parameters"]
    assert any(
        item["name"] == "Idempotency-Key" and item["required"] is True
        for item in parameters
    )
    assert "get" in schema["paths"]["/api/v1/agent/sessions"]
    assert "get" in schema["paths"]["/api/v1/agent/runs"]
    run_list_parameters = schema["paths"]["/api/v1/agent/runs"]["get"]["parameters"]
    assert {"context_type", "context_id"} <= {
        item["name"] for item in run_list_parameters
    }
    assert "get" in schema["paths"]["/api/v1/agent/approvals"]
    assert "get" in schema["paths"]["/api/v1/agent/approvals/{approval_id}"]
    opinion_operation = schema["paths"]["/api/v1/agent/decision-opinions"]["get"]
    assert {
        "strategy_id",
        "strategy_version",
        "trade_date",
        "account_id",
        "sleeve_id",
        "v3_artifact_id",
        "decision_time",
        "knowledge_cutoff",
        "publication_cutoff",
        "source_snapshot_id",
    } == {item["name"] for item in opinion_operation["parameters"]}
    run_schema = schema["components"]["schemas"]["AgentRunResponse"]
    assert {
        "objective",
        "context",
        "output_summary",
        "tool_records",
        "evidence_refs",
        "artifact_refs",
        "guardrail",
        "usage",
        "event_cursor",
        "projection_state",
        "projection_reason",
        "projection_version",
        "projection_updated_at",
    } <= run_schema["properties"].keys()


@pytest.mark.asyncio
async def test_decision_opinion_route_preserves_exact_identity_and_projection() -> None:
    class RecordingQuery:
        def __init__(self) -> None:
            self.identities: list[DecisionOpinionIdentity] = []

        def get_opinion(
            self, identity: DecisionOpinionIdentity
        ) -> DecisionOpinionReadModel:
            self.identities.append(identity)
            return DecisionOpinionReadModel(
                identity=identity,
                status="completed",
                generated_at=datetime(2026, 8, 16, 8, 1, tzinfo=UTC),
                model_profile="balanced",
                summary="V3 remains authoritative.",
                disagreements=("Tail risk deserves review.",),
                uncertainties=("Shadow interpretation only.",),
                evidence_refs=(identity.v3_artifact_id,),
                provenance_match=True,
                shadow_outcome_identity="decision-shadow-1",
                unavailable_reason=None,
            )

    query = RecordingQuery()
    artifact_id = "daily-decision-v3:strategy-1:2026-08-15:account-1:sleeve-1"
    response = await _get_agent_decision_opinion(
        query,
        AgentDecisionOpinionIdentity(
            strategy_id="strategy-1",
            strategy_version="3",
            trade_date="2026-08-15",
            account_id="account-1",
            sleeve_id="sleeve-1",
            v3_artifact_id=artifact_id,
            decision_time=datetime(2026, 8, 16, 8, 0, tzinfo=UTC),
            knowledge_cutoff=datetime(2026, 8, 16, 7, 0, tzinfo=UTC),
            publication_cutoff=datetime(2026, 8, 16, 6, 0, tzinfo=UTC),
            source_snapshot_id="snapshot-1",
        ),
    )

    assert response.data.status == "completed"
    assert response.data.decision_identity.v3_artifact_id == artifact_id
    assert response.data.summary == "V3 remains authoritative."
    assert response.data.provenance_match is True
    assert len(query.identities) == 1
    assert query.identities[0].v3_artifact_id == artifact_id
    assert query.identities[0].context.source_snapshot_id == "snapshot-1"


def test_decision_opinion_query_params_parse_http_protocol_strings() -> None:
    params = AgentDecisionOpinionQueryParams.model_validate_strings(
        {
            "strategy_id": "strategy-1",
            "strategy_version": "3",
            "trade_date": "2026-08-15",
            "account_id": "account-1",
            "sleeve_id": "sleeve-1",
            "v3_artifact_id": (
                "daily-decision-v3:strategy-1:2026-08-15:account-1:sleeve-1"
            ),
            "decision_time": "2026-08-16T08:00:00Z",
            "knowledge_cutoff": "2026-08-16T07:00:00Z",
            "publication_cutoff": "2026-08-16T06:00:00Z",
            "source_snapshot_id": "snapshot-1",
        }
    )

    assert params.strategy_version == "3"
    assert params.decision_time == datetime(2026, 8, 16, 8, 0, tzinfo=UTC)


def test_openapi_registers_fixed_campaign_surface_and_write_fences() -> None:
    schema = create_openapi_app().openapi()
    campaign_paths = {
        "/api/v1/agent/campaigns",
        "/api/v1/agent/campaigns/validation",
        "/api/v1/agent/campaigns/{campaign_id}/approve",
        "/api/v1/agent/campaigns/{campaign_id}",
        "/api/v1/agent/campaigns/{campaign_id}/events",
        "/api/v1/agent/campaigns/{campaign_id}/cancel",
    }

    assert campaign_paths <= schema["paths"].keys()
    assert "get" in schema["paths"]["/api/v1/agent/campaigns"]
    assert "post" in schema["paths"]["/api/v1/agent/campaigns/validation"]
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
    response_schema = schema["components"]["schemas"]["AgentCampaignResponse"]
    assert create_schema["additionalProperties"] is False
    assert approve_schema["additionalProperties"] is False
    assert cancel_schema["additionalProperties"] is False
    assert {
        "objective",
        "output_summary",
        "tool_records",
        "evidence_refs",
        "artifact_refs",
        "guardrail",
        "usage",
        "event_cursor",
        "projection_state",
        "projection_reason",
        "projection_version",
        "projection_updated_at",
    } <= response_schema["properties"].keys()


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
            context=AgentRunContext(
                context_type="daily_decision",
                context_id="strategy-a:paper-a:2026-08-19:artifact-v3",
            ),
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
            context=AgentContextPresentation(
                context_type="daily_decision",
                context_id="strategy-a:paper-a:2026-08-19:artifact-v3",
            ),
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
