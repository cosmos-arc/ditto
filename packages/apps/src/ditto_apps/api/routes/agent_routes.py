"""Thin HTTP and persisted-event SSE adapters for the governed Agent."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Annotated, Never

import orjson
from dishka import FromComponent
from dishka.integrations.fastapi import inject
from ditto_agent.contracts.runtime import ModelProfile, RetentionClass
from ditto_agent.runtime.service import (
    AgentApprovalDecision,
    AgentApprovalDecisionCommand,
    AgentEventView,
    AgentInvalidRequest,
    AgentRequestConflict,
    AgentResourceNotFound,
    AgentRunCancelCommand,
    AgentRunCreateCommand,
    AgentRuntimeError,
    AgentRuntimePort,
    AgentRuntimeUnavailable,
    AgentRunView,
    AgentSessionCreateCommand,
    AgentSessionView,
    ApprovalDecisionKind,
)
from fastapi import APIRouter, Header, Response

from ditto_apps.api.errors import APIError
from ditto_apps.api.mutation_idempotency import IdempotencyKeyHeader
from ditto_apps.models.agent import (
    AgentApprovalDecisionRequest,
    AgentApprovalDecisionResponse,
    AgentRunCancelRequest,
    AgentRunCreateRequest,
    AgentRunResponse,
    AgentSessionCreateRequest,
    AgentSessionResponse,
)
from ditto_apps.models.common import APIResponse

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


def _session_response(session: AgentSessionView) -> AgentSessionResponse:
    return AgentSessionResponse(
        session_id=session.session_id,
        created_at=session.created_at,
        retention_class=session.retention_class,
    )


def _run_response(run: AgentRunView) -> AgentRunResponse:
    return AgentRunResponse(
        run_id=run.run_id,
        session_id=run.session_id,
        status=run.status,
        objective_hash=run.objective_hash,
        authority_hash=run.authority_hash,
        max_model_tokens=run.max_model_tokens,
        max_model_spend_usd=run.max_model_spend_usd,
        model_profile=run.model_profile,
        manifest_hash=run.manifest_hash,
        created_at=run.created_at,
        started_at=run.started_at,
        finished_at=run.finished_at,
        revision=run.revision,
    )


def _approval_response(
    decision: AgentApprovalDecision,
) -> AgentApprovalDecisionResponse:
    return AgentApprovalDecisionResponse(
        approval_id=decision.approval_id,
        run_id=decision.run_id,
        action_hash=decision.action_hash,
        status=decision.status.value,
        operator_id=decision.operator_id,
        reason=decision.reason,
        decided_at=decision.decided_at,
    )


def encode_agent_sse(events: tuple[AgentEventView, ...]) -> bytes:
    """Serialize an ordered persisted replay without creating business events."""
    chunks: list[bytes] = []
    previous_event_id = 0
    for event in events:
        if event.event_id <= previous_event_id:
            raise ValueError("Agent SSE events must have strictly increasing IDs")
        previous_event_id = event.event_id
        data = orjson.dumps(
            {
                "schema_version": event.schema_version,
                "event_id": event.event_id,
                "run_id": event.run_id,
                "run_sequence": event.run_sequence,
                "event_type": event.event_type,
                "payload_hash": event.payload_hash,
                "occurred_at": event.occurred_at,
                "prev_hash": event.prev_hash,
                "event_hash": event.event_hash,
            },
            option=orjson.OPT_SORT_KEYS | orjson.OPT_UTC_Z,
        )
        chunks.append(
            b"".join(
                (
                    f"id: {event.event_id}\n".encode(),
                    f"event: {event.event_type}\n".encode(),
                    b"data: ",
                    data,
                    b"\n\n",
                )
            )
        )
    return b"".join(chunks)


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
            ),
        )
    except AgentRuntimeError as exc:
        _raise_runtime_error(exc)
    return APIResponse(data=_run_response(run))


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


__all__ = ["encode_agent_sse", "router"]
