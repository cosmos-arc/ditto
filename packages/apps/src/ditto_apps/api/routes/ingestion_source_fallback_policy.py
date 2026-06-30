"""Catalog source fallback policy state API route."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Annotated

from dishka import FromComponent
from dishka.integrations.fastapi import inject
from ditto_application.commands.source_fallback_policy import (
    ActivateCatalogSourceFallbackPolicyHandler,
    ApproveCatalogSourceFallbackPolicyHandler,
    CatalogSourceFallbackPolicyDraftCommand,
    CatalogSourceFallbackPolicyLifecycleCommand,
    DraftCatalogSourceFallbackPolicyHandler,
    RetireCatalogSourceFallbackPolicyHandler,
)
from ditto_application.queries.source_fallback_policy_state import (
    CatalogSourceFallbackPolicyQueryFacade,
)
from ditto_application.source_fallback_policy_state import (
    CatalogSourceFallbackPolicy,
    CatalogSourceFallbackPolicyEvent,
    CatalogSourceFallbackPolicyStatus,
)
from fastapi import APIRouter, Query

from ditto_apps.models.common import APIResponse
from ditto_apps.models.source_fallback import (
    CatalogSourceFallbackPolicyDraftRequest,
    CatalogSourceFallbackPolicyEventResponse,
    CatalogSourceFallbackPolicyLifecycleRequest,
    CatalogSourceFallbackPolicyStateResponse,
)

router = APIRouter(tags=["ingestion"])


async def run_blocking[**P, R](
    func: Callable[P, R], /, *args: P.args, **kwargs: P.kwargs
) -> R:
    """Run blocking application work off the event loop."""
    return await asyncio.to_thread(func, *args, **kwargs)


def to_catalog_source_fallback_policy_state_response(
    item: CatalogSourceFallbackPolicy,
) -> CatalogSourceFallbackPolicyStateResponse:
    """Map application source fallback policy state to API response."""
    return CatalogSourceFallbackPolicyStateResponse(
        policy_id=item.policy_id,
        dataset_id=item.dataset_id,
        namespace=item.namespace,
        trade_date=item.trade_date,
        default_source=item.default_source,
        selected_source=item.selected_source,
        recommended_source=item.recommended_source,
        status=item.status,
        created_by=item.created_by,
        created_at=item.created_at.isoformat(),
        recommended_actions=list(item.recommended_actions),
        reason_codes=list(item.reason_codes),
        fallback_sources=list(item.fallback_sources),
        unsupported_sources=list(item.unsupported_sources),
        source_selection_status=item.source_selection_status,
        source_selection_blockers=list(item.source_selection_blockers),
        approval_required=item.approval_required,
        execution_allowed=item.execution_allowed,
        notes=item.notes,
        decided_by=item.decided_by,
        decided_at=item.decided_at.isoformat() if item.decided_at is not None else None,
        decision_notes=item.decision_notes,
    )


def to_catalog_source_fallback_policy_event_response(
    item: CatalogSourceFallbackPolicyEvent,
) -> CatalogSourceFallbackPolicyEventResponse:
    """Map application source fallback policy audit event to API response."""
    return CatalogSourceFallbackPolicyEventResponse(
        policy_id=item.policy_id,
        action=item.action,
        actor=item.actor,
        action_at=item.action_at.isoformat(),
        status=item.status,
        notes=item.notes,
    )


@router.post(
    "/catalog/source-fallback/policies",
    response_model=APIResponse[CatalogSourceFallbackPolicyStateResponse],
)
@inject
async def draft_catalog_source_fallback_policy(
    handler: Annotated[DraftCatalogSourceFallbackPolicyHandler, FromComponent()],
    request: CatalogSourceFallbackPolicyDraftRequest,
) -> APIResponse[CatalogSourceFallbackPolicyStateResponse]:
    """Persist a source fallback policy draft without activating automation."""
    result = await run_blocking(
        handler.handle,
        CatalogSourceFallbackPolicyDraftCommand(
            dataset_id=request.dataset_id,
            namespace=request.namespace,
            trade_date=request.trade_date,
            default_source=request.default_source,
            selected_source=request.selected_source,
            recommended_source=request.recommended_source,
            created_by=request.created_by,
            recommended_actions=tuple(request.recommended_actions),
            reason_codes=tuple(request.reason_codes),
            fallback_sources=tuple(request.fallback_sources),
            unsupported_sources=tuple(request.unsupported_sources),
            source_selection_status=request.source_selection_status,
            source_selection_blockers=tuple(request.source_selection_blockers),
            approval_required=request.approval_required,
            execution_allowed=request.execution_allowed,
            notes=request.notes,
        ),
    )
    return APIResponse(
        data=to_catalog_source_fallback_policy_state_response(result.policy)
    )


@router.get(
    "/catalog/source-fallback/policies",
    response_model=APIResponse[list[CatalogSourceFallbackPolicyStateResponse]],
)
@inject
async def list_catalog_source_fallback_policies(
    facade: Annotated[CatalogSourceFallbackPolicyQueryFacade, FromComponent()],
    dataset_id: str | None = Query(None, description="dataset ID filter"),
    status: CatalogSourceFallbackPolicyStatus | None = Query(
        None,
        description="policy lifecycle status filter",
    ),
) -> APIResponse[list[CatalogSourceFallbackPolicyStateResponse]]:
    """List current source fallback policy states."""
    policies = await run_blocking(
        facade.list_source_fallback_policies,
        dataset_id=dataset_id,
        status=status,
    )
    return APIResponse(
        data=[
            to_catalog_source_fallback_policy_state_response(item) for item in policies
        ]
    )


@router.get(
    "/catalog/source-fallback/policies/{policy_id}",
    response_model=APIResponse[CatalogSourceFallbackPolicyStateResponse],
)
@inject
async def get_catalog_source_fallback_policy(
    facade: Annotated[CatalogSourceFallbackPolicyQueryFacade, FromComponent()],
    policy_id: str,
) -> APIResponse[CatalogSourceFallbackPolicyStateResponse]:
    """Return current source fallback policy state by ID."""
    policy = await run_blocking(
        facade.get_source_fallback_policy,
        policy_id,
    )
    return APIResponse(data=to_catalog_source_fallback_policy_state_response(policy))


@router.get(
    "/catalog/source-fallback/policies/{policy_id}/events",
    response_model=APIResponse[list[CatalogSourceFallbackPolicyEventResponse]],
)
@inject
async def list_catalog_source_fallback_policy_events(
    facade: Annotated[CatalogSourceFallbackPolicyQueryFacade, FromComponent()],
    policy_id: str,
) -> APIResponse[list[CatalogSourceFallbackPolicyEventResponse]]:
    """List append-only audit events for one source fallback policy."""
    events = await run_blocking(
        facade.list_source_fallback_policy_events,
        policy_id,
    )
    return APIResponse(
        data=[to_catalog_source_fallback_policy_event_response(item) for item in events]
    )


@router.post(
    "/catalog/source-fallback/policies/{policy_id}/approval",
    response_model=APIResponse[CatalogSourceFallbackPolicyStateResponse],
)
@inject
async def approve_catalog_source_fallback_policy(
    handler: Annotated[ApproveCatalogSourceFallbackPolicyHandler, FromComponent()],
    policy_id: str,
    request: CatalogSourceFallbackPolicyLifecycleRequest,
) -> APIResponse[CatalogSourceFallbackPolicyStateResponse]:
    """Approve a draft source fallback policy without activating it."""
    result = await run_blocking(
        handler.handle,
        CatalogSourceFallbackPolicyLifecycleCommand(
            policy_id=policy_id,
            actor=request.actor,
            notes=request.notes,
        ),
    )
    return APIResponse(
        data=to_catalog_source_fallback_policy_state_response(result.policy)
    )


@router.post(
    "/catalog/source-fallback/policies/{policy_id}/activation",
    response_model=APIResponse[CatalogSourceFallbackPolicyStateResponse],
)
@inject
async def activate_catalog_source_fallback_policy(
    handler: Annotated[ActivateCatalogSourceFallbackPolicyHandler, FromComponent()],
    policy_id: str,
    request: CatalogSourceFallbackPolicyLifecycleRequest,
) -> APIResponse[CatalogSourceFallbackPolicyStateResponse]:
    """Activate an approved source fallback policy resource only."""
    result = await run_blocking(
        handler.handle,
        CatalogSourceFallbackPolicyLifecycleCommand(
            policy_id=policy_id,
            actor=request.actor,
            notes=request.notes,
        ),
    )
    return APIResponse(
        data=to_catalog_source_fallback_policy_state_response(result.policy)
    )


@router.post(
    "/catalog/source-fallback/policies/{policy_id}/retirement",
    response_model=APIResponse[CatalogSourceFallbackPolicyStateResponse],
)
@inject
async def retire_catalog_source_fallback_policy(
    handler: Annotated[RetireCatalogSourceFallbackPolicyHandler, FromComponent()],
    policy_id: str,
    request: CatalogSourceFallbackPolicyLifecycleRequest,
) -> APIResponse[CatalogSourceFallbackPolicyStateResponse]:
    """Retire an active source fallback policy resource."""
    result = await run_blocking(
        handler.handle,
        CatalogSourceFallbackPolicyLifecycleCommand(
            policy_id=policy_id,
            actor=request.actor,
            notes=request.notes,
        ),
    )
    return APIResponse(
        data=to_catalog_source_fallback_policy_state_response(result.policy)
    )
