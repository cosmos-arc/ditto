"""R5.1 Agent HTTP contract and thin route behavior."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from ditto_agent.contracts.execution import AgentRunExecutionPlan
from ditto_agent.contracts.runtime import ModelProfile, RetentionClass, RunStatus
from ditto_agent.contracts.temporal import (
    EgressClass,
    TemporalContextInput,
    TemporalToolContext,
)
from ditto_agent.presentation import AgentContextPresentation
from ditto_agent.runtime.service import (
    AgentApprovalDecision,
    AgentApprovalDecisionCommand,
    AgentApprovalListView,
    AgentApprovalStatus,
    AgentApprovalView,
    AgentCapabilityView,
    AgentEventView,
    AgentRequestConflict,
    AgentRunCancelCommand,
    AgentRunCreateCommand,
    AgentRunExecuteCommand,
    AgentRunListView,
    AgentRuntimePort,
    AgentRuntimeState,
    AgentRuntimeUnavailable,
    AgentRunView,
    AgentSessionCreateCommand,
    AgentSessionListView,
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
    execute_agent_run,
    get_agent_decision_opinion,
)
from ditto_apps.models.agent import (
    AgentDecisionOpinionQueryParams,
    AgentRunCancelRequest,
    AgentRunContext,
    AgentRunCreateRequest,
    AgentRunExecuteRequest,
    AgentRunExecutionScope,
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
_execute_agent_run = getattr(
    execute_agent_run, "__dishka_orig_func__", execute_agent_run
)
_get_agent_decision_opinion = getattr(
    get_agent_decision_opinion,
    "__dishka_orig_func__",
    get_agent_decision_opinion,
)


class _RecordingRuntime(AgentRuntimePort):
    def __init__(self) -> None:
        self.commands: list[object] = []

    def get_capabilities(self) -> AgentCapabilityView:
        return AgentCapabilityView(
            enabled=True,
            runtime_state=AgentRuntimeState.AVAILABLE,
            provider="test-provider",
            available_profiles=(ModelProfile.BALANCED,),
            default_profile=ModelProfile.BALANCED,
            degradation_reason=None,
            checked_at=_NOW,
        )

    def list_sessions(self, *, limit: int, offset: int) -> AgentSessionListView:
        return AgentSessionListView(items=(), total=0, limit=limit, offset=offset)

    def list_runs(
        self,
        *,
        status: RunStatus | None,
        session_id: str | None,
        context_type: str | None,
        context_id: str | None,
        limit: int,
        offset: int,
    ) -> AgentRunListView:
        del status, session_id, context_type, context_id
        return AgentRunListView(items=(), total=0, limit=limit, offset=offset)

    def get_approval(self, approval_id: str) -> AgentApprovalView:
        return AgentApprovalView(
            approval_id=approval_id,
            run_id="run-1",
            action_type="test_action",
            target_identity="test-target",
            action_payload={},
            action_hash=_HASH,
            status=AgentApprovalStatus.PENDING,
            requested_at=_NOW,
            expires_at=_NOW,
            operator_id=None,
            reason=None,
            decided_at=None,
        )

    def list_approvals(
        self,
        *,
        status: AgentApprovalStatus | None,
        run_id: str | None,
        limit: int,
        offset: int,
    ) -> AgentApprovalListView:
        del status, run_id
        return AgentApprovalListView(items=(), total=0, limit=limit, offset=offset)

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

    async def execute_run(self, command: AgentRunExecuteCommand) -> AgentRunView:
        self.commands.append(command)
        return _run_view(status=RunStatus.COMPLETED, revision=2)

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
        "/api/v1/agent/runs/{run_id}/execute",
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
        "X-Ditto-API-Contract-Version",
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

    stream_content = schema["paths"]["/api/v1/agent/runs/{run_id}/events"]["get"][
        "responses"
    ]["200"]["content"]["text/event-stream"]
    assert stream_content["schema"] == {"type": "string"}
    assert stream_content["x-ditto-sse-data-schema"] == {
        "$ref": "#/components/schemas/AgentRunSseEvent"
    }
    assert stream_content["x-ditto-sse-terminal"] == {
        "field": "event_type",
        "values": [
            "approval_resume_completed",
            "run_completed",
            "run_failed",
            "run_cancelled",
        ],
    }
    assert schema["paths"]["/api/v1/agent/runs/{run_id}/events"]["get"]["responses"][
        "410"
    ]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/ErrorResponse"
    }
    run_event_schema = schema["components"]["schemas"]["AgentRunSseEvent"]
    assert run_event_schema["properties"]["schema_version"]["const"] == 1


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
        AgentDecisionOpinionQueryParams(
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

    stream_content = schema["paths"]["/api/v1/agent/campaigns/{campaign_id}/events"][
        "get"
    ]["responses"]["200"]["content"]["text/event-stream"]
    assert stream_content["schema"] == {"type": "string"}
    assert stream_content["x-ditto-sse-data-schema"] == {
        "$ref": "#/components/schemas/AgentCampaignSseEvent"
    }
    assert stream_content["x-ditto-sse-terminal"] == {
        "field": "event_type",
        "values": [
            "campaign_completed",
            "campaign_cancelled",
        ],
    }
    assert schema["paths"]["/api/v1/agent/campaigns/{campaign_id}/events"]["get"][
        "responses"
    ]["410"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/ErrorResponse"
    }
    campaign_event_schema = schema["components"]["schemas"]["AgentCampaignSseEvent"]
    assert campaign_event_schema["properties"]["schema_version"]["const"] == 1


@pytest.mark.asyncio
async def test_create_routes_translate_dtos_to_runtime_commands() -> None:
    runtime = _RecordingRuntime()

    session = await _create_agent_session(
        AgentSessionCreateRequest(retention_class="audit"),
        runtime,
        "session-key",
    )
    scope = AgentRunExecutionScope(
        decision_time=datetime(2026, 8, 30, 8, tzinfo=UTC),
        knowledge_cutoff=datetime(2026, 8, 30, 7, tzinfo=UTC),
        publication_cutoff=datetime(2026, 8, 30, 6, tzinfo=UTC),
        source_snapshot_id="snapshot-certified-2026-08-29",
        allowed_universe=("510300.SH",),
        max_output_tokens=256,
    )
    run = await _create_agent_run(
        AgentRunCreateRequest(
            session_id="session-1",
            objective="Explain the frozen evidence.",
            max_model_tokens=512,
            max_model_spend_usd=Decimal("0.25"),
            model_profile="balanced",
            execution_scope=scope,
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
    plan = AgentRunExecutionPlan(
        temporal_context=TemporalToolContext.from_host(
            TemporalContextInput(
                decision_time=scope.decision_time,
                knowledge_cutoff=scope.knowledge_cutoff,
                publication_cutoff=scope.publication_cutoff,
                source_snapshot_id=scope.source_snapshot_id,
                execution_eligible_at="not_applicable",
                allowed_universe=scope.allowed_universe,
                license_class="approved-research",
                egress_class=EgressClass.CLOUD_ALLOWED,
            )
        ),
        allowed_tools=(
            "daily_decision_v3_evidence",
            "portfolio_evidence",
            "risk_evidence",
        ),
        max_output_tokens=256,
    )
    assert runtime.commands == [
        AgentSessionCreateCommand(
            retention_class=RetentionClass.AUDIT,
            idempotency_key="session-key",
        ),
        AgentRunCreateCommand(
            session_id="session-1",
            objective="Explain the frozen evidence.",
            authority_hash=plan.authority_hash,
            max_model_tokens=512,
            max_model_spend_usd=Decimal("0.25"),
            model_profile=ModelProfile.BALANCED,
            idempotency_key="run-key",
            context=AgentContextPresentation(
                context_type="daily_decision",
                context_id="strategy-a:paper-a:2026-08-19:artifact-v3",
            ),
            execution_plan=plan,
        ),
    ]


@pytest.mark.asyncio
async def test_market_context_run_is_narrowed_to_market_context_evidence() -> None:
    runtime = _RecordingRuntime()
    scope = AgentRunExecutionScope(
        decision_time=datetime(2026, 8, 31, 9, tzinfo=UTC),
        knowledge_cutoff=datetime(2026, 8, 31, 8, tzinfo=UTC),
        publication_cutoff=datetime(2026, 8, 31, 7, 30, tzinfo=UTC),
        source_snapshot_id="snapshot-set:sha256:market",
        allowed_universe=("market-context",),
        max_output_tokens=512,
    )

    await _create_agent_run(
        AgentRunCreateRequest(
            session_id="session-1",
            objective="Create a cited MarketContext EvidenceBrief.",
            max_model_tokens=1024,
            max_model_spend_usd=Decimal("0.25"),
            model_profile="balanced",
            execution_scope=scope,
            context=AgentRunContext(
                context_type="market_context",
                context_id="market-regime:sha256:abc",
            ),
        ),
        runtime,
        "market-brief-1",
    )

    command = runtime.commands[0]
    assert isinstance(command, AgentRunCreateCommand)
    plan = command.execution_plan
    assert plan is not None
    assert plan.allowed_tools == ("market_context_evidence",)


@pytest.mark.asyncio
async def test_instrument_run_is_narrowed_to_technical_evidence() -> None:
    runtime = _RecordingRuntime()
    scope = AgentRunExecutionScope(
        decision_time=datetime(2026, 8, 31, 9, tzinfo=UTC),
        knowledge_cutoff=datetime(2026, 8, 31, 8, tzinfo=UTC),
        publication_cutoff=datetime(2026, 8, 31, 7, tzinfo=UTC),
        source_snapshot_id="snapshot-stock",
        allowed_universe=("600519.SH",),
        max_output_tokens=512,
    )

    await _create_agent_run(
        AgentRunCreateRequest(
            session_id="session-1",
            objective="Create a cited TechnicalAnalysisBrief for 600519.SH.",
            max_model_tokens=1024,
            max_model_spend_usd=Decimal("0.25"),
            model_profile="balanced",
            execution_scope=scope,
            context=AgentRunContext(
                context_type="instrument",
                context_id="600519.SH",
            ),
        ),
        runtime,
        "technical-brief-1",
    )

    command = runtime.commands[0]
    assert isinstance(command, AgentRunCreateCommand)
    plan = command.execution_plan
    assert plan is not None
    assert plan.allowed_tools == ("instrument_technical_evidence",)


@pytest.mark.asyncio
async def test_unknown_context_type_is_rejected_instead_of_receiving_all_tools() -> (
    None
):
    runtime = _RecordingRuntime()
    scope = AgentRunExecutionScope(
        decision_time=datetime(2026, 8, 31, 9, tzinfo=UTC),
        knowledge_cutoff=datetime(2026, 8, 31, 8, tzinfo=UTC),
        publication_cutoff=datetime(2026, 8, 31, 7, 30, tzinfo=UTC),
        source_snapshot_id="snapshot-stock",
        allowed_universe=("600519.SH",),
        max_output_tokens=512,
    )

    with pytest.raises(APIError) as exc_info:
        await _create_agent_run(
            AgentRunCreateRequest(
                session_id="session-1",
                objective="Try an unrecognized capability context.",
                max_model_tokens=1024,
                max_model_spend_usd=Decimal("0.25"),
                model_profile="balanced",
                execution_scope=scope,
                context=AgentRunContext(
                    context_type="model-invented-context",
                    context_id="unsafe",
                ),
            ),
            runtime,
            "unknown-context-1",
        )

    assert exc_info.value.status_code == 422
    assert runtime.commands == []


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
async def test_execute_route_preserves_revision_fence() -> None:
    runtime = _RecordingRuntime()

    response = await _execute_agent_run(
        "run-1",
        AgentRunExecuteRequest(expected_revision=0),
        runtime,
    )

    assert response.data.status is RunStatus.COMPLETED
    assert runtime.commands == [
        AgentRunExecuteCommand(run_id="run-1", expected_revision=0)
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
                execution_scope=AgentRunExecutionScope(
                    decision_time=datetime(2026, 8, 30, 8, tzinfo=UTC),
                    knowledge_cutoff=datetime(2026, 8, 30, 7, tzinfo=UTC),
                    publication_cutoff=datetime(2026, 8, 30, 6, tzinfo=UTC),
                    source_snapshot_id="snapshot-certified-2026-08-29",
                    allowed_universe=("510300.SH",),
                ),
            ),
            DisabledRuntime(),
            "run-key",
        )
    assert unavailable.value.status_code == 503
    assert unavailable.value.error_code == "AGENT_UNAVAILABLE"
