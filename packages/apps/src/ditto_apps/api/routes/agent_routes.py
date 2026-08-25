"""Thin HTTP and persisted-event SSE adapters for the governed Agent."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Annotated, Never

from dishka import FromComponent
from dishka.integrations.fastapi import inject
from ditto_agent.contracts.runtime import ModelProfile, RetentionClass, RunStatus
from ditto_agent.presentation import AgentContextPresentation
from ditto_agent.runtime.service import (
    AgentApprovalDecisionCommand,
    AgentApprovalStatus,
    AgentInvalidRequest,
    AgentRequestConflict,
    AgentResourceNotFound,
    AgentRunCancelCommand,
    AgentRunCreateCommand,
    AgentRuntimeError,
    AgentRuntimePort,
    AgentRuntimeUnavailable,
    AgentSessionCreateCommand,
    ApprovalDecisionKind,
)
from ditto_application.agent_campaign_runtime import (
    CampaignApproveCommand,
    CampaignCancelCommand,
    CampaignCreateCommand,
    CampaignInvalidRequest,
    CampaignRequestConflict,
    CampaignResourceNotFound,
    CampaignRuntimeError,
    CampaignRuntimePort,
    CampaignRuntimeUnavailable,
    CampaignStatus,
    CampaignValidationCommand,
)
from ditto_application.exceptions import AppQueryError
from ditto_application.queries.decision_opinion import (
    DecisionOpinionIdentity,
    DecisionOpinionQueryPort,
)
from ditto_application.queries.evidence_contracts import EvidenceTemporalContext
from fastapi import APIRouter, Header, Query, Response

from ditto_apps.api.errors import APIError
from ditto_apps.api.mutation_idempotency import IdempotencyKeyHeader
from ditto_apps.api.routes.agent_presenters import (
    approval_detail_response as _approval_detail_response,
)
from ditto_apps.api.routes.agent_presenters import (
    approval_response as _approval_response,
)
from ditto_apps.api.routes.agent_presenters import (
    campaign_response as _campaign_response,
)
from ditto_apps.api.routes.agent_presenters import (
    campaign_validation_response as _campaign_validation_response,
)
from ditto_apps.api.routes.agent_presenters import (
    capability_response as _capability_response,
)
from ditto_apps.api.routes.agent_presenters import (
    decision_opinion_response as _decision_opinion_response,
)
from ditto_apps.api.routes.agent_presenters import (
    encode_agent_sse,
    encode_campaign_sse,
)
from ditto_apps.api.routes.agent_presenters import (
    run_response as _run_response,
)
from ditto_apps.api.routes.agent_presenters import (
    session_response as _session_response,
)
from ditto_apps.models.agent import (
    AgentApprovalDecisionRequest,
    AgentApprovalDecisionResponse,
    AgentApprovalResponse,
    AgentCampaignApproveRequest,
    AgentCampaignCancelRequest,
    AgentCampaignCreateRequest,
    AgentCampaignResponse,
    AgentCampaignValidationRequest,
    AgentCampaignValidationResponse,
    AgentCapabilityResponse,
    AgentDecisionOpinionQueryParams,
    AgentDecisionOpinionResponse,
    AgentRunCancelRequest,
    AgentRunCreateRequest,
    AgentRunResponse,
    AgentSessionCreateRequest,
    AgentSessionResponse,
)
from ditto_apps.models.common import APIResponse, PaginationResponse

router = APIRouter(prefix="/agent", tags=["agent"])
LastEventIdHeader = Annotated[int | None, Header(alias="Last-Event-ID", ge=0)]


async def _run_blocking[**P, R](
    func: Callable[P, R], /, *args: P.args, **kwargs: P.kwargs
) -> R:
    return await asyncio.to_thread(func, *args, **kwargs)


def _raise_runtime_error(exc: AgentRuntimeError) -> Never:
    if isinstance(exc, AgentRuntimeUnavailable):
        raise APIError(
            str(exc), status_code=503, error_code="AGENT_UNAVAILABLE"
        ) from exc
    if isinstance(exc, AgentResourceNotFound):
        raise APIError(
            str(exc), status_code=404, error_code=exc.reason_code.upper()
        ) from exc
    if isinstance(exc, AgentRequestConflict):
        raise APIError(
            str(exc), status_code=409, error_code=exc.reason_code.upper()
        ) from exc
    if isinstance(exc, AgentInvalidRequest):
        raise APIError(
            str(exc), status_code=422, error_code=exc.reason_code.upper()
        ) from exc
    raise APIError(
        "Agent runtime failed", status_code=500, error_code=exc.reason_code.upper()
    ) from exc


def _raise_campaign_error(exc: CampaignRuntimeError) -> Never:
    if isinstance(exc, CampaignRuntimeUnavailable):
        raise APIError(
            str(exc), status_code=503, error_code=exc.reason_code.upper()
        ) from exc
    if isinstance(exc, CampaignResourceNotFound):
        raise APIError(
            str(exc), status_code=404, error_code=exc.reason_code.upper()
        ) from exc
    if isinstance(exc, CampaignRequestConflict):
        raise APIError(
            str(exc), status_code=409, error_code=exc.reason_code.upper()
        ) from exc
    if isinstance(exc, CampaignInvalidRequest):
        raise APIError(
            str(exc), status_code=422, error_code=exc.reason_code.upper()
        ) from exc
    raise APIError(
        "Campaign runtime failed",
        status_code=500,
        error_code=exc.reason_code.upper(),
    ) from exc


@router.get(
    "/capabilities",
    response_model=APIResponse[AgentCapabilityResponse],
)
@inject
async def get_agent_capabilities(
    runtime: Annotated[AgentRuntimePort, FromComponent()],
) -> APIResponse[AgentCapabilityResponse]:
    """Read Agent availability without exposing provider configuration secrets."""
    try:
        capability = await _run_blocking(runtime.get_capabilities)
    except AgentRuntimeError as exc:
        _raise_runtime_error(exc)
    return APIResponse(data=_capability_response(capability))


@router.get(
    "/decision-opinions",
    response_model=APIResponse[AgentDecisionOpinionResponse],
)
@inject
async def get_agent_decision_opinion(
    query: Annotated[DecisionOpinionQueryPort, FromComponent()],
    request_identity: Annotated[AgentDecisionOpinionQueryParams, Query()],
) -> APIResponse[AgentDecisionOpinionResponse]:
    """Read one shadow opinion only through its exact V3 and PIT identity."""
    try:
        identity = DecisionOpinionIdentity(
            strategy_id=request_identity.strategy_id,
            strategy_version=request_identity.strategy_version,
            trade_date=request_identity.trade_date,
            account_id=request_identity.account_id,
            sleeve_id=request_identity.sleeve_id,
            v3_artifact_id=request_identity.v3_artifact_id,
            context=EvidenceTemporalContext(
                decision_time=request_identity.decision_time,
                knowledge_cutoff=request_identity.knowledge_cutoff,
                publication_cutoff=request_identity.publication_cutoff,
                source_snapshot_id=request_identity.source_snapshot_id,
            ),
        )
        opinion = await _run_blocking(query.get_opinion, identity)
    except AppQueryError as exc:
        raise APIError(
            "DecisionOpinion identity is invalid",
            status_code=422,
            error_code="DECISION_OPINION_IDENTITY_INVALID",
        ) from exc
    return APIResponse(data=_decision_opinion_response(opinion))


@router.get(
    "/sessions",
    response_model=APIResponse[list[AgentSessionResponse]],
)
@inject
async def list_agent_sessions(
    runtime: Annotated[AgentRuntimePort, FromComponent()],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> APIResponse[list[AgentSessionResponse]]:
    """Recover durable Agent sessions without caller-held identities."""
    try:
        page = await _run_blocking(
            runtime.list_sessions,
            limit=limit,
            offset=offset,
        )
    except AgentRuntimeError as exc:
        _raise_runtime_error(exc)
    return APIResponse(
        data=[_session_response(item) for item in page.items],
        pagination=PaginationResponse(
            total=page.total,
            limit=page.limit,
            offset=page.offset,
        ),
    )


@router.post(
    "/sessions",
    response_model=APIResponse[AgentSessionResponse],
    status_code=201,
)
@inject
async def create_agent_session(
    request: AgentSessionCreateRequest,
    runtime: Annotated[AgentRuntimePort, FromComponent()],
    idempotency_key: IdempotencyKeyHeader,
) -> APIResponse[AgentSessionResponse]:
    """Create or exactly replay a local Agent session."""
    try:
        session = await _run_blocking(
            runtime.create_session,
            AgentSessionCreateCommand(
                retention_class=RetentionClass(request.retention_class),
                idempotency_key=idempotency_key,
            ),
        )
    except AgentRuntimeError as exc:
        _raise_runtime_error(exc)
    return APIResponse(data=_session_response(session))


@router.post(
    "/runs",
    response_model=APIResponse[AgentRunResponse],
    status_code=201,
)
@inject
async def create_agent_run(
    request: AgentRunCreateRequest,
    runtime: Annotated[AgentRuntimePort, FromComponent()],
    idempotency_key: IdempotencyKeyHeader,
) -> APIResponse[AgentRunResponse]:
    """Create or exactly replay one governed read-only run."""
    try:
        run = await _run_blocking(
            runtime.create_run,
            AgentRunCreateCommand(
                session_id=request.session_id,
                objective=request.objective,
                authority_hash=request.authority_hash,
                max_model_tokens=request.max_model_tokens,
                max_model_spend_usd=request.max_model_spend_usd,
                model_profile=ModelProfile(request.model_profile),
                idempotency_key=idempotency_key,
                context=(
                    AgentContextPresentation(
                        context_type=request.context.context_type,
                        context_id=request.context.context_id,
                    )
                    if request.context is not None
                    else None
                ),
            ),
        )
    except AgentRuntimeError as exc:
        _raise_runtime_error(exc)
    return APIResponse(data=_run_response(run))


@router.get(
    "/runs",
    response_model=APIResponse[list[AgentRunResponse]],
)
@inject
async def list_agent_runs(
    runtime: Annotated[AgentRuntimePort, FromComponent()],
    status: Annotated[RunStatus | None, Query()] = None,
    session_id: Annotated[str | None, Query(min_length=1, max_length=512)] = None,
    context_type: Annotated[str | None, Query(min_length=1, max_length=128)] = None,
    context_id: Annotated[str | None, Query(min_length=1, max_length=1024)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> APIResponse[list[AgentRunResponse]]:
    """Recover durable Agent runs with bounded equality filters."""
    try:
        page = await _run_blocking(
            runtime.list_runs,
            status=status,
            session_id=session_id,
            context_type=context_type,
            context_id=context_id,
            limit=limit,
            offset=offset,
        )
    except AgentRuntimeError as exc:
        _raise_runtime_error(exc)
    return APIResponse(
        data=[_run_response(item) for item in page.items],
        pagination=PaginationResponse(
            total=page.total,
            limit=page.limit,
            offset=page.offset,
        ),
    )


@router.get(
    "/runs/{run_id}",
    response_model=APIResponse[AgentRunResponse],
)
@inject
async def get_agent_run(
    run_id: str,
    runtime: Annotated[AgentRuntimePort, FromComponent()],
) -> APIResponse[AgentRunResponse]:
    """Read one non-sensitive persisted run projection."""
    try:
        run = await _run_blocking(runtime.get_run, run_id)
    except AgentRuntimeError as exc:
        _raise_runtime_error(exc)
    return APIResponse(data=_run_response(run))


@router.get(
    "/runs/{run_id}/events",
    response_model=None,
    response_class=Response,
    responses={200: {"content": {"text/event-stream": {}}}},
)
@inject
async def get_agent_run_events(
    run_id: str,
    runtime: Annotated[AgentRuntimePort, FromComponent()],
    last_event_id: LastEventIdHeader = None,
) -> Response:
    """Replay persisted run events after Last-Event-ID without executing tools."""
    try:
        events = await _run_blocking(
            runtime.list_run_events,
            run_id,
            after_event_id=last_event_id,
        )
    except AgentRuntimeError as exc:
        _raise_runtime_error(exc)
    return Response(
        content=encode_agent_sse(events),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post(
    "/runs/{run_id}/cancel",
    response_model=APIResponse[AgentRunResponse],
)
@inject
async def cancel_agent_run(
    run_id: str,
    request: AgentRunCancelRequest,
    runtime: Annotated[AgentRuntimePort, FromComponent()],
) -> APIResponse[AgentRunResponse]:
    """Cancel one queued/running run under an optimistic revision fence."""
    try:
        run = await _run_blocking(
            runtime.cancel_run,
            AgentRunCancelCommand(
                run_id=run_id,
                expected_revision=request.expected_revision,
            ),
        )
    except AgentRuntimeError as exc:
        _raise_runtime_error(exc)
    return APIResponse(data=_run_response(run))


@router.get(
    "/approvals",
    response_model=APIResponse[list[AgentApprovalResponse]],
)
@inject
async def list_agent_approvals(
    runtime: Annotated[AgentRuntimePort, FromComponent()],
    status: Annotated[AgentApprovalStatus | None, Query()] = None,
    run_id: Annotated[str | None, Query(min_length=1, max_length=512)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> APIResponse[list[AgentApprovalResponse]]:
    """List exact approval subjects including pending and expired states."""
    try:
        page = await _run_blocking(
            runtime.list_approvals,
            status=status,
            run_id=run_id,
            limit=limit,
            offset=offset,
        )
    except AgentRuntimeError as exc:
        _raise_runtime_error(exc)
    return APIResponse(
        data=[_approval_detail_response(item) for item in page.items],
        pagination=PaginationResponse(
            total=page.total,
            limit=page.limit,
            offset=page.offset,
        ),
    )


@router.get(
    "/approvals/{approval_id}",
    response_model=APIResponse[AgentApprovalResponse],
)
@inject
async def get_agent_approval(
    approval_id: str,
    runtime: Annotated[AgentRuntimePort, FromComponent()],
) -> APIResponse[AgentApprovalResponse]:
    """Read one exact action payload, hash, expiry, and decision state."""
    try:
        approval = await _run_blocking(runtime.get_approval, approval_id)
    except AgentRuntimeError as exc:
        _raise_runtime_error(exc)
    return APIResponse(data=_approval_detail_response(approval))


@router.post(
    "/approvals/{approval_id}/decision",
    response_model=APIResponse[AgentApprovalDecisionResponse],
)
@inject
async def decide_agent_approval(
    approval_id: str,
    request: AgentApprovalDecisionRequest,
    runtime: Annotated[AgentRuntimePort, FromComponent()],
) -> APIResponse[AgentApprovalDecisionResponse]:
    """Record a human approve/reject decision for one exact action hash."""
    try:
        decision = await _run_blocking(
            runtime.decide_approval,
            AgentApprovalDecisionCommand(
                approval_id=approval_id,
                expected_action_hash=request.expected_action_hash,
                decision=ApprovalDecisionKind(request.decision),
                operator_id=request.operator_id,
                reason=request.reason,
            ),
        )
    except AgentRuntimeError as exc:
        _raise_runtime_error(exc)
    return APIResponse(data=_approval_response(decision))


@router.post(
    "/campaigns",
    response_model=APIResponse[AgentCampaignResponse],
    status_code=201,
)
@inject
async def create_agent_campaign(
    request: AgentCampaignCreateRequest,
    runtime: Annotated[CampaignRuntimePort, FromComponent()],
    idempotency_key: IdempotencyKeyHeader,
) -> APIResponse[AgentCampaignResponse]:
    """Create or recover one immutable Campaign draft."""
    try:
        campaign = await _run_blocking(
            runtime.create_campaign,
            CampaignCreateCommand(
                manifest_document=request.manifest.model_dump(mode="python"),
                idempotency_key=idempotency_key,
            ),
        )
    except (ValueError, CampaignRuntimeError) as exc:
        if isinstance(exc, CampaignRuntimeError):
            _raise_campaign_error(exc)
        _raise_campaign_error(
            CampaignInvalidRequest(
                "Campaign request is invalid",
                reason_code="campaign_request_invalid",
            )
        )
    return APIResponse(data=_campaign_response(campaign))


@router.post(
    "/campaigns/validation",
    response_model=APIResponse[AgentCampaignValidationResponse],
)
@inject
async def validate_agent_campaign(
    request: AgentCampaignValidationRequest,
    runtime: Annotated[CampaignRuntimePort, FromComponent()],
) -> APIResponse[AgentCampaignValidationResponse]:
    """Validate one structured wizard step without creating durable state."""
    try:
        validation = await _run_blocking(
            runtime.validate_campaign,
            CampaignValidationCommand(
                step=request.step,
                document=request.model_dump(mode="python", exclude={"step"}),
            ),
        )
    except (ValueError, CampaignRuntimeError) as exc:
        if isinstance(exc, CampaignRuntimeError):
            _raise_campaign_error(exc)
        _raise_campaign_error(
            CampaignInvalidRequest(
                "Campaign validation request is invalid",
                reason_code="campaign_manifest_invalid",
            )
        )
    return APIResponse(data=_campaign_validation_response(validation))


@router.get(
    "/campaigns",
    response_model=APIResponse[list[AgentCampaignResponse]],
)
@inject
async def list_agent_campaigns(
    runtime: Annotated[CampaignRuntimePort, FromComponent()],
    status: Annotated[CampaignStatus | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> APIResponse[list[AgentCampaignResponse]]:
    """Recover durable Campaign projections without caller-held identities."""
    try:
        page = await _run_blocking(
            runtime.list_campaigns,
            status=status,
            limit=limit,
            offset=offset,
        )
    except CampaignRuntimeError as exc:
        _raise_campaign_error(exc)
    return APIResponse(
        data=[_campaign_response(item) for item in page.items],
        pagination=PaginationResponse(
            total=page.total,
            limit=page.limit,
            offset=page.offset,
        ),
    )


@router.post(
    "/campaigns/{campaign_id}/approve",
    response_model=APIResponse[AgentCampaignResponse],
)
@inject
async def approve_agent_campaign(
    campaign_id: str,
    request: AgentCampaignApproveRequest,
    runtime: Annotated[CampaignRuntimePort, FromComponent()],
    idempotency_key: IdempotencyKeyHeader,
) -> APIResponse[AgentCampaignResponse]:
    """Approve one exact immutable manifest and finite budget."""
    try:
        campaign = await _run_blocking(
            runtime.approve_campaign,
            CampaignApproveCommand(
                campaign_id=campaign_id,
                expected_manifest_hash=request.expected_manifest_hash,
                operator_id=request.operator_id,
                expires_at=request.expires_at,
                idempotency_key=idempotency_key,
            ),
        )
    except (ValueError, CampaignRuntimeError) as exc:
        if isinstance(exc, CampaignRuntimeError):
            _raise_campaign_error(exc)
        _raise_campaign_error(
            CampaignInvalidRequest(
                "Campaign approval request is invalid",
                reason_code="campaign_request_invalid",
            )
        )
    return APIResponse(data=_campaign_response(campaign))


@router.get(
    "/campaigns/{campaign_id}",
    response_model=APIResponse[AgentCampaignResponse],
)
@inject
async def get_agent_campaign(
    campaign_id: str,
    runtime: Annotated[CampaignRuntimePort, FromComponent()],
) -> APIResponse[AgentCampaignResponse]:
    """Read one persisted Campaign projection."""
    try:
        campaign = await _run_blocking(runtime.get_campaign, campaign_id)
    except CampaignRuntimeError as exc:
        _raise_campaign_error(exc)
    return APIResponse(data=_campaign_response(campaign))


@router.get(
    "/campaigns/{campaign_id}/events",
    response_model=None,
    response_class=Response,
    responses={200: {"content": {"text/event-stream": {}}}},
)
@inject
async def get_agent_campaign_events(
    campaign_id: str,
    runtime: Annotated[CampaignRuntimePort, FromComponent()],
    last_event_id: LastEventIdHeader = None,
) -> Response:
    """Replay persisted Campaign events after Last-Event-ID."""
    try:
        events = await _run_blocking(
            runtime.list_campaign_events,
            campaign_id,
            after_event_id=last_event_id,
        )
    except CampaignRuntimeError as exc:
        _raise_campaign_error(exc)
    return Response(
        content=encode_campaign_sse(events),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post(
    "/campaigns/{campaign_id}/cancel",
    response_model=APIResponse[AgentCampaignResponse],
)
@inject
async def cancel_agent_campaign(
    campaign_id: str,
    request: AgentCampaignCancelRequest,
    runtime: Annotated[CampaignRuntimePort, FromComponent()],
    idempotency_key: IdempotencyKeyHeader,
) -> APIResponse[AgentCampaignResponse]:
    """Cancel or recover cancellation under exact immutable authority."""
    try:
        campaign = await _run_blocking(
            runtime.cancel_campaign,
            CampaignCancelCommand(
                campaign_id=campaign_id,
                expected_authorization_hash=request.expected_authorization_hash,
                idempotency_key=idempotency_key,
            ),
        )
    except (ValueError, CampaignRuntimeError) as exc:
        if isinstance(exc, CampaignRuntimeError):
            _raise_campaign_error(exc)
        _raise_campaign_error(
            CampaignInvalidRequest(
                "Campaign cancellation request is invalid",
                reason_code="campaign_request_invalid",
            )
        )
    return APIResponse(data=_campaign_response(campaign))


__all__ = ["encode_agent_sse", "encode_campaign_sse", "router"]
