"""Catalog remediation API route."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Annotated

from dishka import FromComponent
from dishka.integrations.fastapi import inject
from ditto_application.commands.catalog_remediation import (
    CatalogRemediationApprovalDecisionCommand,
    CatalogRemediationApprovalExecutionCommand,
    CatalogRemediationApprovalRequestCommand,
    DecideCatalogRemediationApprovalHandler,
    ExecuteCatalogRemediationApprovalHandler,
    RequestCatalogRemediationApprovalHandler,
)
from ditto_application.config import get_all_datasets
from ditto_application.queries.catalog import CatalogSourceFallbackPolicyEffect
from ditto_application.queries.remediation import (
    CatalogRemediationApprovalIntent,
    CatalogRemediationBacklogReport,
    CatalogRemediationEvidenceRequirement,
    CatalogRemediationItem,
    CatalogRemediationItemDetail,
    CatalogRemediationQueryFacade,
    CatalogRemediationReasonCount,
    CatalogRemediationSeverityCount,
    CatalogRemediationSourceCount,
    CatalogRemediationSourceFallbackPolicyEffectCount,
)
from ditto_application.queries.remediation_approval import (
    CatalogRemediationApprovalQueryFacade,
)
from ditto_application.remediation_approval import (
    CatalogRemediationActionExecution,
    CatalogRemediationApproval,
    CatalogRemediationApprovalEvent,
    CatalogRemediationApprovalStatus,
)
from fastapi import APIRouter, Query

from ditto_apps.models.common import APIResponse
from ditto_apps.models.ingestion import CatalogSourceFallbackPolicyEffectResponse
from ditto_apps.models.remediation import (
    CatalogRemediationActionExecutionResponse,
    CatalogRemediationApprovalDecisionRequest,
    CatalogRemediationApprovalEventResponse,
    CatalogRemediationApprovalExecutionRequest,
    CatalogRemediationApprovalExecutionResponse,
    CatalogRemediationApprovalIntentResponse,
    CatalogRemediationApprovalRequest,
    CatalogRemediationApprovalResponse,
    CatalogRemediationBacklogResponse,
    CatalogRemediationEvidenceRequirementResponse,
    CatalogRemediationItemDetailResponse,
    CatalogRemediationItemResponse,
    CatalogRemediationReasonCountResponse,
    CatalogRemediationSeverityCountResponse,
    CatalogRemediationSourceCountResponse,
    CatalogRemediationSourceFallbackPolicyEffectCountResponse,
)

router = APIRouter(tags=["ingestion"])


async def run_blocking[**P, R](
    func: Callable[P, R], /, *args: P.args, **kwargs: P.kwargs
) -> R:
    """Run blocking application work off the event loop."""
    return await asyncio.to_thread(func, *args, **kwargs)


_KNOWN_DATASETS = [dataset.value for dataset in get_all_datasets()]


def to_catalog_remediation_severity_count_response(
    item: CatalogRemediationSeverityCount,
) -> CatalogRemediationSeverityCountResponse:
    """Map application remediation severity count to API response."""
    return CatalogRemediationSeverityCountResponse(
        severity=item.severity,
        count=item.count,
    )


def to_catalog_remediation_source_count_response(
    item: CatalogRemediationSourceCount,
) -> CatalogRemediationSourceCountResponse:
    """Map application remediation source count to API response."""
    return CatalogRemediationSourceCountResponse(
        source=item.source,
        count=item.count,
    )


def to_catalog_remediation_reason_count_response(
    item: CatalogRemediationReasonCount,
) -> CatalogRemediationReasonCountResponse:
    """Map application remediation reason count to API response."""
    return CatalogRemediationReasonCountResponse(
        source=item.source,
        reason=item.reason,
        count=item.count,
    )


def to_catalog_remediation_source_fallback_policy_effect_count_response(
    item: CatalogRemediationSourceFallbackPolicyEffectCount,
) -> CatalogRemediationSourceFallbackPolicyEffectCountResponse:
    """Map application remediation policy effect count to API response."""
    return CatalogRemediationSourceFallbackPolicyEffectCountResponse(
        policy_id=item.policy_id,
        policy_status=item.policy_status,
        catalog_selected_source=item.catalog_selected_source,
        effective_selected_source=item.effective_selected_source,
        count=item.count,
    )


def to_catalog_remediation_evidence_requirement_response(
    item: CatalogRemediationEvidenceRequirement,
) -> CatalogRemediationEvidenceRequirementResponse:
    """Map application remediation evidence requirement to API response."""
    return CatalogRemediationEvidenceRequirementResponse(
        requirement_id=item.requirement_id,
        source=item.source,
        status=item.status,
        description=item.description,
    )


def to_catalog_remediation_approval_intent_response(
    item: CatalogRemediationApprovalIntent,
) -> CatalogRemediationApprovalIntentResponse:
    """Map application remediation approval intent to API response."""
    return CatalogRemediationApprovalIntentResponse(
        action=item.action,
        intent_type=item.intent_type,
        method=item.method,
        path=item.path,
        request_template=item.request_template,
        required_operator_inputs=list(item.required_operator_inputs),
        notes=item.notes,
    )


def to_catalog_source_fallback_policy_effect_response(
    item: CatalogSourceFallbackPolicyEffect | None,
) -> CatalogSourceFallbackPolicyEffectResponse | None:
    """Map application fallback policy effect evidence to API response."""
    if item is None:
        return None
    return CatalogSourceFallbackPolicyEffectResponse(
        policy_id=item.policy_id,
        policy_status=item.policy_status,
        catalog_selected_source=item.catalog_selected_source,
        effective_selected_source=item.effective_selected_source,
        reason_codes=list(item.reason_codes),
        recommended_actions=list(item.recommended_actions),
    )


def to_catalog_remediation_approval_response(
    item: CatalogRemediationApproval,
) -> CatalogRemediationApprovalResponse:
    """Map application remediation approval state to API response."""
    return CatalogRemediationApprovalResponse(
        approval_id=item.approval_id,
        item_id=item.item_id,
        action=item.action,
        status=item.status,
        requested_by=item.requested_by,
        requested_at=item.requested_at.isoformat(),
        intent_type=item.intent_type,
        method=item.method,
        path=item.path,
        request_payload=item.request_payload,
        authority_hash=item.authority_hash,
        expires_at=item.expires_at.isoformat(),
        notes=item.notes,
        decided_by=item.decided_by,
        decided_at=item.decided_at.isoformat() if item.decided_at is not None else None,
        decision_notes=item.decision_notes,
    )


def to_catalog_remediation_approval_event_response(
    item: CatalogRemediationApprovalEvent,
) -> CatalogRemediationApprovalEventResponse:
    """Map application remediation approval audit event to API response."""
    return CatalogRemediationApprovalEventResponse(
        approval_id=item.approval_id,
        action=item.action,
        actor=item.actor,
        action_at=item.action_at.isoformat(),
        status=item.status,
        notes=item.notes,
    )


def to_catalog_remediation_action_execution_response(
    item: CatalogRemediationActionExecution,
) -> CatalogRemediationActionExecutionResponse:
    """Map application remediation action execution to API response."""
    return CatalogRemediationActionExecutionResponse(
        approval_id=item.approval_id,
        action=item.action,
        status=item.status,
        executed_by=item.executed_by,
        executed_at=item.executed_at.isoformat(),
        result_payload=item.result_payload,
        notes=item.notes,
    )


def to_catalog_remediation_item_response(
    item: CatalogRemediationItem,
) -> CatalogRemediationItemResponse:
    """Map application remediation item to API response."""
    return CatalogRemediationItemResponse(
        item_id=item.item_id,
        source=item.source,
        dataset_id=item.dataset_id,
        namespace=item.namespace,
        severity=item.severity,
        reasons=list(item.reasons),
        suggested_actions=list(item.suggested_actions),
        trade_date=item.trade_date,
        run_id=item.run_id,
        side=item.side,
        partition_keys=list(item.partition_keys),
        default_source=item.default_source,
        selected_source=item.selected_source,
        fallback_sources=list(item.fallback_sources),
        source_fallback_policy_effect=(
            to_catalog_source_fallback_policy_effect_response(
                item.source_fallback_policy_effect
            )
        ),
        source_selection_status=item.source_selection_status,
        source_selection_blockers=list(item.source_selection_blockers),
        current_maturity=item.current_maturity,
        promotion_status=item.promotion_status,
        catalog_status=item.catalog_status,
        freshness_status=item.freshness_status,
    )


def to_catalog_remediation_item_detail_response(
    detail: CatalogRemediationItemDetail,
) -> CatalogRemediationItemDetailResponse:
    """Map application remediation item detail to API response."""
    return CatalogRemediationItemDetailResponse(
        generated_at=detail.generated_at.isoformat(),
        item=to_catalog_remediation_item_response(detail.item),
        summary=detail.summary,
        evidence_requirements=[
            to_catalog_remediation_evidence_requirement_response(item)
            for item in detail.evidence_requirements
        ],
        approval_intents=[
            to_catalog_remediation_approval_intent_response(item)
            for item in detail.approval_intents
        ],
    )


def to_catalog_remediation_backlog_response(
    report: CatalogRemediationBacklogReport,
) -> CatalogRemediationBacklogResponse:
    """Map application remediation backlog to API response."""
    return CatalogRemediationBacklogResponse(
        generated_at=report.generated_at.isoformat(),
        dataset_ids=list(report.dataset_ids),
        trade_dates=list(report.trade_dates),
        available_sources=list(report.available_sources),
        run_id=report.run_id,
        total_items=report.total_items,
        severity_counts=[
            to_catalog_remediation_severity_count_response(item)
            for item in report.severity_counts
        ],
        source_counts=[
            to_catalog_remediation_source_count_response(item)
            for item in report.source_counts
        ],
        reason_counts=[
            to_catalog_remediation_reason_count_response(item)
            for item in report.reason_counts
        ],
        source_fallback_policy_effect_counts=[
            to_catalog_remediation_source_fallback_policy_effect_count_response(item)
            for item in report.source_fallback_policy_effect_counts
        ],
        items=[to_catalog_remediation_item_response(item) for item in report.items],
    )


@router.post(
    "/catalog/remediation/approvals",
    response_model=APIResponse[CatalogRemediationApprovalResponse],
    operation_id="ingestion_request_catalog_remediation_approval",
)
@inject
async def request_catalog_remediation_approval(
    handler: Annotated[RequestCatalogRemediationApprovalHandler, FromComponent()],
    request: CatalogRemediationApprovalRequest,
) -> APIResponse[CatalogRemediationApprovalResponse]:
    """Persist a remediation approval request without executing the intent."""
    result = await run_blocking(
        handler.handle,
        CatalogRemediationApprovalRequestCommand(
            item_id=request.item_id,
            action=request.action,
            requested_by=request.requested_by,
            intent_type=request.intent_type,
            method=request.method,
            path=request.path,
            request_payload=request.request_payload,
            notes=request.notes,
        ),
    )
    return APIResponse(data=to_catalog_remediation_approval_response(result.approval))


@router.post(
    "/catalog/remediation/approvals/{approval_id}/decision",
    response_model=APIResponse[CatalogRemediationApprovalResponse],
    operation_id="ingestion_decide_catalog_remediation_approval",
)
@inject
async def decide_catalog_remediation_approval(
    handler: Annotated[DecideCatalogRemediationApprovalHandler, FromComponent()],
    approval_id: str,
    request: CatalogRemediationApprovalDecisionRequest,
) -> APIResponse[CatalogRemediationApprovalResponse]:
    """Approve or reject a pending remediation approval without executing it."""
    result = await run_blocking(
        handler.handle,
        CatalogRemediationApprovalDecisionCommand(
            approval_id=approval_id,
            expected_authority_hash=request.authority_hash,
            decision=request.decision,
            decided_by=request.decided_by,
            notes=request.notes,
        ),
    )
    return APIResponse(data=to_catalog_remediation_approval_response(result.approval))


@router.post(
    "/catalog/remediation/approvals/{approval_id}/execute",
    response_model=APIResponse[CatalogRemediationApprovalExecutionResponse],
    operation_id="ingestion_execute_catalog_remediation_approval",
)
@inject
async def execute_catalog_remediation_approval(
    handler: Annotated[ExecuteCatalogRemediationApprovalHandler, FromComponent()],
    approval_id: str,
    request: CatalogRemediationApprovalExecutionRequest,
) -> APIResponse[CatalogRemediationApprovalExecutionResponse]:
    """Execute an approved remediation action through application orchestration."""
    result = await run_blocking(
        handler.handle,
        CatalogRemediationApprovalExecutionCommand(
            approval_id=approval_id,
            expected_authority_hash=request.authority_hash,
            executed_by=request.executed_by,
            notes=request.notes,
        ),
    )
    return APIResponse(
        data=CatalogRemediationApprovalExecutionResponse(
            approval=to_catalog_remediation_approval_response(result.approval),
            execution=to_catalog_remediation_action_execution_response(
                result.execution
            ),
        )
    )


@router.get(
    "/catalog/remediation/approvals/{approval_id}/events",
    response_model=APIResponse[list[CatalogRemediationApprovalEventResponse]],
    operation_id="ingestion_list_catalog_remediation_approval_events",
)
@inject
async def list_catalog_remediation_approval_events(
    facade: Annotated[CatalogRemediationApprovalQueryFacade, FromComponent()],
    approval_id: str,
) -> APIResponse[list[CatalogRemediationApprovalEventResponse]]:
    """List append-only audit events for one remediation approval."""
    events = await run_blocking(
        facade.list_remediation_approval_events,
        approval_id,
    )
    return APIResponse(
        data=[to_catalog_remediation_approval_event_response(item) for item in events]
    )


@router.get(
    "/catalog/remediation/approvals/{approval_id}",
    response_model=APIResponse[CatalogRemediationApprovalResponse],
    operation_id="ingestion_get_catalog_remediation_approval",
)
@inject
async def get_catalog_remediation_approval(
    facade: Annotated[CatalogRemediationApprovalQueryFacade, FromComponent()],
    approval_id: str,
) -> APIResponse[CatalogRemediationApprovalResponse]:
    """Return current remediation approval state by ID."""
    approval = await run_blocking(
        facade.get_remediation_approval,
        approval_id,
    )
    return APIResponse(data=to_catalog_remediation_approval_response(approval))


@router.get(
    "/catalog/remediation/approvals",
    response_model=APIResponse[list[CatalogRemediationApprovalResponse]],
    operation_id="ingestion_list_catalog_remediation_approvals",
)
@inject
async def list_catalog_remediation_approvals(
    facade: Annotated[CatalogRemediationApprovalQueryFacade, FromComponent()],
    item_id: str | None = Query(None, description="remediation backlog item ID"),
    status: CatalogRemediationApprovalStatus | None = Query(
        None,
        description="approval status filter",
    ),
) -> APIResponse[list[CatalogRemediationApprovalResponse]]:
    """List current remediation approval states."""
    approvals = await run_blocking(
        facade.list_remediation_approvals,
        item_id=item_id,
        status=status,
    )
    return APIResponse(
        data=[to_catalog_remediation_approval_response(item) for item in approvals]
    )


@router.get(
    "/catalog/remediation/backlog",
    response_model=APIResponse[CatalogRemediationBacklogResponse],
    operation_id="ingestion_get_catalog_remediation_backlog",
)
@inject
async def get_catalog_remediation_backlog(
    facade: Annotated[CatalogRemediationQueryFacade, FromComponent()],
    dataset_ids: list[str] | None = Query(
        None,
        description="数据集 ID 列表; 缺省使用当前后端已知数据集集合",
    ),
    trade_dates: list[str] = Query(..., description="交易日期列表"),
    available_sources: list[str] | None = Query(
        None,
        description="source=auto 可用来源列表; 缺省使用当前后端默认数据源集合",
    ),
    run_id: str | None = Query(
        None,
        description=(
            "可选 backtest run ID; 提供后会并入 run-level lineage catalog attention"
        ),
    ),
) -> APIResponse[CatalogRemediationBacklogResponse]:
    """Return backend-owned catalog remediation backlog."""
    report = await run_blocking(
        facade.get_remediation_backlog,
        dataset_ids=tuple(dataset_ids or _KNOWN_DATASETS),
        trade_dates=tuple(trade_dates),
        available_sources=tuple(available_sources or ("tushare", "fred")),
        run_id=run_id,
    )
    return APIResponse(data=to_catalog_remediation_backlog_response(report))


@router.get(
    "/catalog/remediation/items/{item_id}",
    response_model=APIResponse[CatalogRemediationItemDetailResponse],
    operation_id="ingestion_get_catalog_remediation_item_detail",
)
@inject
async def get_catalog_remediation_item_detail(
    facade: Annotated[CatalogRemediationQueryFacade, FromComponent()],
    item_id: str,
    dataset_ids: list[str] | None = Query(
        None,
        description="数据集 ID 列表; 缺省使用当前后端已知数据集集合",
    ),
    trade_dates: list[str] = Query(..., description="交易日期列表"),
    available_sources: list[str] | None = Query(
        None,
        description="source=auto 可用来源列表; 缺省使用当前后端默认数据源集合",
    ),
    run_id: str | None = Query(
        None,
        description=(
            "可选 backtest run ID; 提供后会并入 run-level lineage catalog attention"
        ),
    ),
) -> APIResponse[CatalogRemediationItemDetailResponse]:
    """Return backend-owned remediation item detail and next-step intents."""
    detail = await run_blocking(
        facade.get_remediation_item_detail,
        item_id=item_id,
        dataset_ids=tuple(dataset_ids or _KNOWN_DATASETS),
        trade_dates=tuple(trade_dates),
        available_sources=tuple(available_sources or ("tushare", "fred")),
        run_id=run_id,
    )
    return APIResponse(data=to_catalog_remediation_item_detail_response(detail))
