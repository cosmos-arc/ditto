"""Isolated HTTP app for the R1-R5 frontend live-acceptance pass.

This composition root is intentionally test-only.  It exposes the production
Agent router over real SQLite runtimes while refusing every data root outside
``/tmp`` and every environment other than ``testing``.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from dishka import Provider, Scope, make_async_container, provide
from dishka.integrations.fastapi import setup_dishka
from ditto_agent.contracts.approval import (
    ActionBudget,
    ApprovalAction,
    ApprovalRequest,
)
from ditto_agent.contracts.runtime import (
    AgentManifest,
    ModelProfile,
    RetentionClass,
)
from ditto_agent.contracts.temporal import (
    EgressClass,
    TemporalContextInput,
    TemporalToolContext,
)
from ditto_agent.presentation import AgentContextPresentation
from ditto_agent.runtime.service import (
    AgentRunCreateCommand,
    AgentRuntimePort,
    AgentSessionCreateCommand,
)
from ditto_analysis.experiments.models import ExperimentId
from ditto_analysis.experiments.persistence import LeaseFence
from ditto_analysis.storage.sqlite.experiments import (
    ResearchExperimentDatabase,
    SQLiteCampaignReader,
    SQLiteCampaignWriter,
)
from ditto_application.agent_campaign_runtime import CampaignRuntimePort
from ditto_application.processes.experiments._autonomous_campaign_contracts import (
    CampaignScheduledTrial,
    CampaignTrialRetryRequest,
    CampaignTrialScheduleRequest,
    CampaignTrialSchedulerPort,
)
from ditto_application.processes.experiments.autonomous_campaign import (
    AutonomousCampaignCoordinator,
)
from ditto_application.queries.decision_opinion import (
    DecisionOpinionIdentity,
    DecisionOpinionQueryPort,
    DecisionOpinionReadModel,
)
from ditto_apps.api.errors import APIError
from ditto_apps.api.routes.agent_routes import router
from ditto_apps.middleware import api_error_handler
from ditto_apps.registry.agent.campaign_runtime import PersistedCampaignRuntime
from ditto_apps.registry.agent.database_provider import build_agent_database
from ditto_apps.registry.agent.runtime import (
    PersistedAgentRuntime,
    PersistedAgentRuntimeOptions,
)
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

_HASH_A = "a" * 64
_HASH_B = "b" * 64


def _data_root() -> Path:
    if os.environ.get("DITTO_ENVIRONMENT") != "testing":
        raise RuntimeError("live acceptance app requires DITTO_ENVIRONMENT=testing")
    raw = os.environ.get("DITTO_ACCEPTANCE_DATA_ROOT")
    if raw is None:
        raise RuntimeError("DITTO_ACCEPTANCE_DATA_ROOT is required")
    root = Path(raw).resolve()
    if not root.is_relative_to(Path("/tmp").resolve()):
        raise RuntimeError("live acceptance data root must be inside /tmp")
    root.mkdir(parents=True, exist_ok=True)
    return root


class _Scheduler(CampaignTrialSchedulerPort):
    """Deterministic scheduling boundary; persistence remains production code."""

    @staticmethod
    def _lease(campaign_id: ExperimentId, now_epoch_us: int) -> LeaseFence:
        return LeaseFence(
            experiment_id=campaign_id,
            owner_token="frontend-live-acceptance",
            revision=1,
            lease_until_epoch_us=now_epoch_us + 60_000_000,
        )

    def required_fold_run_count(self, campaign_id: ExperimentId) -> int:
        return 2

    def schedule_trial(
        self,
        request: CampaignTrialScheduleRequest,
        *,
        now_epoch_us: int,
    ) -> CampaignScheduledTrial:
        return CampaignScheduledTrial(
            lease=self._lease(request.campaign_id, now_epoch_us),
            fold_run_count=2,
        )

    def schedule_retry(
        self,
        request: CampaignTrialRetryRequest,
        *,
        now_epoch_us: int,
    ) -> LeaseFence:
        return self._lease(request.campaign_id, now_epoch_us)

    def cancel_campaign(
        self,
        campaign_id: ExperimentId,
        *,
        now_epoch_us: int,
    ) -> None:
        del campaign_id, now_epoch_us


_root = _data_root()
_agent_database = build_agent_database(_root)
_manifest = AgentManifest(
    manifest_id="frontend-live-acceptance",
    agent_version="r5-live-acceptance",
    prompt_version="acceptance-v1",
    prompt_hash=_HASH_A,
    tool_schema_version="governed-read-only-v1",
    tool_schema_hash=_HASH_B,
    model_profile=ModelProfile.BALANCED,
    model_snapshot="controlled-no-provider-call",
)
_agent_database.writer.put_manifest(_manifest)


def _clock() -> datetime:
    return datetime.now(UTC)


_agent_runtime = PersistedAgentRuntime(
    reader=_agent_database.reader,
    writer=_agent_database.writer,
    manifest=_manifest,
    clock=_clock,
    options=PersistedAgentRuntimeOptions(
        provider_name="controlled-persisted-runtime",
        presentation_reader=_agent_database.presentation_reader,
        presentation_writer=_agent_database.presentation_writer,
    ),
)
_session = _agent_runtime.create_session(
    AgentSessionCreateCommand(
        retention_class=RetentionClass.AUDIT,
        idempotency_key="frontend-live-seeded-session",
    )
)
_seeded_run = _agent_runtime.create_run(
    AgentRunCreateCommand(
        session_id=_session.session_id,
        objective="Review the exact experiment evidence before authoring.",
        authority_hash=_HASH_A,
        max_model_tokens=4_096,
        max_model_spend_usd=Decimal("1.50"),
        model_profile=ModelProfile.BALANCED,
        idempotency_key="frontend-live-seeded-run",
        context=AgentContextPresentation(
            context_type="experiment",
            context_id="experiment-live@revision-4",
        ),
    )
)
_now = _clock()
_temporal_context = TemporalToolContext.from_host(
    TemporalContextInput(
        decision_time=_now,
        knowledge_cutoff=_now - timedelta(minutes=5),
        publication_cutoff=_now - timedelta(minutes=10),
        source_snapshot_id="snapshot-live-acceptance",
        execution_eligible_at="not_applicable",
        allowed_universe=("510300.SH",),
        license_class="controlled-research",
        egress_class=EgressClass.LOCAL_ONLY,
    )
)


def _approval_request(
    *, request_id: str, target_identity: str, before: str, after: str
) -> ApprovalRequest:
    return ApprovalRequest.issue(
        request_id=request_id,
        run_id=_seeded_run.run_id,
        action=ApprovalAction(
            action_kind="formal_author_write",
            tool_name="author_save_strategy_draft",
            parameters={
                "changes": [
                    {
                        "operation": "replace",
                        "path": "/name",
                        "before": before,
                        "after": after,
                    }
                ],
                "evidence_refs": ["daily-decision-v3:live"],
                "artifact_hash": _HASH_B,
                "validation": "passed",
                "guardrail": "passed",
            },
            subject_identity=target_identity,
            required_authority="strategy.author",
            authority_hash=_HASH_A,
            temporal_context=_temporal_context,
            budget=ActionBudget(
                max_tool_calls=1,
                max_output_bytes=16_384,
                max_model_tokens=512,
                max_model_spend_usd=Decimal("0.20"),
            ),
            expires_at=_now + timedelta(hours=4),
        ),
    )


_approval = _approval_request(
    request_id="approval-live-author",
    target_identity="strategy-live@4",
    before="Momentum v4",
    after="Momentum v5",
)
_rejection_approval = _approval_request(
    request_id="approval-live-author-reject",
    target_identity="strategy-live@5",
    before="Momentum v5",
    after="Momentum v6",
)
_agent_database.writer.create_approval(_approval, requested_at=_now)
_agent_database.writer.create_approval(_rejection_approval, requested_at=_now)

_research_database = ResearchExperimentDatabase(_root)
_research_database.initialize()
_campaign_reader = SQLiteCampaignReader(_research_database)
_campaign_runtime = PersistedCampaignRuntime(
    coordinator=AutonomousCampaignCoordinator(
        reader=_campaign_reader,
        writer=SQLiteCampaignWriter(_research_database),
        scheduler=_Scheduler(),
    ),
    reader=_campaign_reader,
    idempotency_reader=_agent_database.reader,
    idempotency_writer=_agent_database.writer,
    clock=_clock,
)


class _ControlledDecisionOpinionQuery:
    """Deterministic shadow-only success projection for the live UI boundary."""

    def get_opinion(
        self,
        identity: DecisionOpinionIdentity,
    ) -> DecisionOpinionReadModel:
        return DecisionOpinionReadModel(
            identity=identity,
            status="completed",
            generated_at=identity.context.decision_time + timedelta(minutes=2),
            model_profile="balanced",
            summary=(
                "Risk evidence is coherent; keep the shadow interpretation "
                "separate from execution."
            ),
            disagreements=(
                "Tail loss remains material under the market crash scenario.",
            ),
            uncertainties=(
                "Opening-gap behavior is not present in the current evidence.",
            ),
            evidence_refs=(identity.v3_artifact_id,),
            provenance_match=True,
            shadow_outcome_identity="decision-shadow-live-acceptance",
            unavailable_reason=None,
        )


_opinion_query = _ControlledDecisionOpinionQuery()


class _AcceptanceProvider(Provider):
    scope = Scope.APP

    @provide
    def agent_runtime(self) -> AgentRuntimePort:
        return _agent_runtime

    @provide
    def campaign_runtime(self) -> CampaignRuntimePort:
        return _campaign_runtime

    @provide
    def opinion_query(self) -> DecisionOpinionQueryPort:
        return _opinion_query


_container = make_async_container(_AcceptanceProvider())


@asynccontextmanager
async def _lifespan(_: FastAPI) -> AsyncIterator[None]:
    yield
    await _container.close()
    _agent_database.close()
    _research_database.close_all()


app = FastAPI(title="Ditto isolated frontend live acceptance", lifespan=_lifespan)
setup_dishka(container=_container, app=app)
app.include_router(router, prefix="/api/v1")
app.add_exception_handler(APIError, api_error_handler)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID"],
)


@app.middleware("http")
async def _request_identity(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    request_id = request.headers.get("X-Request-ID") or f"acceptance-{uuid4()}"
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    with (_root / "requests.log").open("a", encoding="utf-8") as stream:
        stream.write(
            f"{_clock().isoformat()} {request_id} {request.method} "
            f"{request.url.path} {response.status_code}\n"
        )
    return response


@app.get("/healthz")
async def healthz() -> dict[str, object]:
    return {
        "status": "ok",
        "environment": "testing",
        "data_root": str(_root),
        "seeded_run_id": _seeded_run.run_id,
        "seeded_approval_ids": [
            _approval.request_id,
            _rejection_approval.request_id,
        ],
    }
