"""
策略 API 路由.

端点:
- POST   /strategies                          创建策略
- GET    /strategies                          列出策略
- GET    /strategies/{id}                     获取策略详情
- PUT    /strategies/{id}                     更新策略
- GET    /strategies/{id}/versions            governance 版本历史
- GET    /strategies/{id}/active              active pointer + payload
- POST   /strategies/{id}/versions/{v}/submit-review   提交审查
- POST   /strategies/{id}/versions/{v}/approve         审批
- POST   /strategies/{id}/versions/{v}/reject          驳回
- POST   /strategies/{id}/versions/{v}/deprecate       弃用
- POST   /strategies/{id}/versions/{v}/reactivate      重新激活（乐观 CAS）
- POST   /strategies/{id}/versions/{v}/publish         证据门控发布
- POST   /strategies/{id}/versions/{v}/validate        candidate spec pre-save 校验
- GET    /strategies/{id}/versions/{v}/diff            版本 spec diff（vs parent）
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Annotated, Never

from dishka import FromComponent
from dishka.integrations.fastapi import inject
from ditto_application.commands.strategy import (
    CreateStrategyCommand,
    CreateStrategyHandler,
    UpdateStrategyCommand,
    UpdateStrategyHandler,
)
from ditto_application.commands.strategy_governance import (
    ApproveReviewCommand,
    ApproveReviewHandler,
    DeprecateStrategyCommand,
    DeprecateStrategyHandler,
    PublishStrategyVersionCommand,
    PublishStrategyVersionHandler,
    ReactivateStrategyCommand,
    ReactivateStrategyHandler,
    RejectReviewCommand,
    RejectReviewHandler,
    SubmitReviewCommand,
    SubmitReviewHandler,
)
from ditto_application.contracts import (
    StrategyActiveInfo,
    StrategyActivePointerInfo,
    StrategySpecInfo,
    StrategySpecValidationInfo,
    StrategyVersionDiffInfo,
    StrategyVersionInfo,
    StrategyVersionStateInfo,
)
from ditto_application.exceptions import AppError
from ditto_application.queries.strategy import StrategyQueryFacade
from fastapi import APIRouter, Depends

from ditto_apps.api.deps import paginate, pagination_params
from ditto_apps.api.errors import (
    ConflictError,
    NotFoundError,
    UnprocessableEntityError,
    raise_business_error,
)
from ditto_apps.models.common import APIResponse, PaginationRequest
from ditto_apps.models.strategy import (
    CreateStrategyRequest,
    GovernanceDecisionRequest,
    PublishStrategyVersionRequest,
    ReactivateStrategyRequest,
    SpecChangeResponse,
    StrategyActivePointerResponse,
    StrategyActiveResponse,
    StrategyResponse,
    StrategySpecValidateRequest,
    StrategySpecValidationResponse,
    StrategyVersionDiffResponse,
    StrategyVersionResponse,
    StrategyVersionStateResponse,
    UpdateStrategyRequest,
)

router = APIRouter(prefix="/strategies", tags=["strategies"])

#: Governance decision error messages carrying these keywords map to 409.
_CONFLICT_KEYWORDS = ("conflict",)


def _raise_publish_error(exc: AppError) -> Never:
    """Preserve typed evidence and atomic-CAS failures at the HTTP boundary."""
    reason = exc.details.get("reason")
    if isinstance(reason, str) and reason:
        raise UnprocessableEntityError(str(exc), error_code=reason) from exc
    code = exc.details.get("code")
    if isinstance(code, str) and code == "STRATEGY_REVISION_CONFLICT":
        raise ConflictError(str(exc), error_code=code) from exc
    raise_business_error(exc, conflict_keywords=_CONFLICT_KEYWORDS)


def _raise_reactivate_error(exc: AppError) -> Never:
    """Map the typed guarded-reactivation failures to stable HTTP semantics."""
    code = exc.details.get("code")
    if not isinstance(code, str):
        raise_business_error(exc, conflict_keywords=_CONFLICT_KEYWORDS)
    if code == "STRATEGY_REVISION_CONFLICT":
        raise ConflictError(str(exc), error_code=code) from exc
    if code == "STRATEGY_VERSION_NOT_FOUND":
        raise NotFoundError(str(exc)) from exc
    if code in {
        "STRATEGY_REACTIVATION_CONFIRMATION_MISMATCH",
        "STRATEGY_REACTIVATION_INPUT_INVALID",
        "STRATEGY_INVALID_TRANSITION",
    }:
        raise UnprocessableEntityError(str(exc), error_code=code) from exc
    raise_business_error(exc, conflict_keywords=_CONFLICT_KEYWORDS)


async def run_blocking[**P, R](
    func: Callable[P, R], /, *args: P.args, **kwargs: P.kwargs
) -> R:
    """Run blocking application work off the event loop."""
    return await asyncio.to_thread(func, *args, **kwargs)


def to_strategy_response(info: StrategySpecInfo) -> StrategyResponse:
    """将 App StrategySpecInfo 转为 API 响应."""
    return StrategyResponse(
        strategy_id=info.strategy_id,
        name=info.name,
        spec_json=dict(info.spec_json),
        version=info.version,
        status=info.status,
        created_at=info.created_at,
        tags=list(info.tags),
    )


def to_version_response(info: StrategyVersionInfo) -> StrategyVersionResponse:
    """将 governance 版本投影转为 API 响应（不含 payload bytes）."""
    return StrategyVersionResponse(
        strategy_id=info.strategy_id,
        version=info.version,
        parent_version=info.parent_version,
        spec_hash=info.spec_hash,
        state=info.state,
        review_outcome=info.review_outcome,
        created_at=info.created_at,
    )


def to_version_state_response(
    record: StrategyVersionStateInfo,
) -> StrategyVersionStateResponse:
    """将 governance 状态机结果转为 API 响应."""
    return StrategyVersionStateResponse(
        strategy_id=record.strategy_id,
        version=record.version,
        state=record.state,
        review_outcome=record.review_outcome,
    )


def to_active_response(active: StrategyActiveInfo) -> StrategyActiveResponse:
    """将 active pointer + payload 转为 API 响应."""
    return StrategyActiveResponse(
        strategy_id=active.strategy_id,
        active_version=active.active_version,
        pointer_revision=active.pointer_revision,
        spec=to_strategy_response(active.spec),
    )


def to_active_pointer_response(
    pointer: StrategyActivePointerInfo,
) -> StrategyActivePointerResponse:
    """将 active pointer 转为 API 响应（reactivate 后）."""
    return StrategyActivePointerResponse(
        strategy_id=pointer.strategy_id,
        active_version=pointer.active_version,
        pointer_revision=pointer.pointer_revision,
    )


@router.post("", response_model=APIResponse[StrategyResponse])
@inject
async def create_strategy(
    request: CreateStrategyRequest,
    handler: Annotated[CreateStrategyHandler, FromComponent()],
) -> APIResponse[StrategyResponse]:
    """创建策略."""
    cmd = CreateStrategyCommand(
        strategy_id=request.strategy_id,
        name=request.name,
        spec_json=request.spec_json,
        tags=tuple(request.tags),
    )
    info = await run_blocking(handler.handle, cmd)
    return APIResponse(data=to_strategy_response(info))


@router.get("", response_model=APIResponse[list[StrategyResponse]])
@inject
async def list_strategies(
    facade: Annotated[StrategyQueryFacade, FromComponent()],
    pagination: PaginationRequest = Depends(pagination_params),
) -> APIResponse[list[StrategyResponse]]:
    """列出策略."""
    specs = await run_blocking(facade.list_specs)
    return paginate([to_strategy_response(s) for s in specs], pagination)


@router.get("/{strategy_id}", response_model=APIResponse[StrategyResponse])
@inject
async def get_strategy(
    strategy_id: str,
    facade: Annotated[StrategyQueryFacade, FromComponent()],
) -> APIResponse[StrategyResponse]:
    """获取策略详情."""
    info = await run_blocking(facade.get_spec, strategy_id)
    if info is None:
        raise NotFoundError(f"Strategy not found: {strategy_id}")
    return APIResponse(data=to_strategy_response(info))


@router.put("/{strategy_id}", response_model=APIResponse[StrategyResponse])
@inject
async def update_strategy(
    strategy_id: str,
    request: UpdateStrategyRequest,
    handler: Annotated[UpdateStrategyHandler, FromComponent()],
) -> APIResponse[StrategyResponse]:
    """更新策略."""
    cmd = UpdateStrategyCommand(
        strategy_id=strategy_id,
        name=request.name,
        spec_json=request.spec_json,
        version=request.version,
        tags=tuple(request.tags),
    )
    try:
        info = await run_blocking(handler.handle, cmd)
    except (AppError, ValueError) as exc:
        raise_business_error(exc, conflict_keywords=("conflict",))
    return APIResponse(data=to_strategy_response(info))


@router.get(
    "/{strategy_id}/versions",
    response_model=APIResponse[list[StrategyVersionResponse]],
)
@inject
async def list_strategy_versions(
    strategy_id: str,
    facade: Annotated[StrategyQueryFacade, FromComponent()],
) -> APIResponse[list[StrategyVersionResponse]]:
    """列出策略的 governance 版本历史（newest first）."""
    versions = await run_blocking(facade.list_versions, strategy_id)
    return APIResponse(data=[to_version_response(v) for v in versions])


@router.get(
    "/{strategy_id}/active",
    response_model=APIResponse[StrategyActiveResponse],
)
@inject
async def get_active_strategy(
    strategy_id: str,
    facade: Annotated[StrategyQueryFacade, FromComponent()],
) -> APIResponse[StrategyActiveResponse]:
    """获取 active pointer + published payload；无 active pointer 返回 404."""
    active = await run_blocking(facade.get_active, strategy_id)
    if active is None:
        raise NotFoundError(f"Active strategy not found: {strategy_id}")
    return APIResponse(data=to_active_response(active))


@router.post(
    "/{strategy_id}/versions/{version}/submit-review",
    response_model=APIResponse[StrategyVersionStateResponse],
)
@inject
async def submit_strategy_review(
    strategy_id: str,
    version: int,
    request: GovernanceDecisionRequest,
    handler: Annotated[SubmitReviewHandler, FromComponent()],
) -> APIResponse[StrategyVersionStateResponse]:
    """提交策略版本审查."""
    cmd = SubmitReviewCommand(
        strategy_id=strategy_id,
        version=version,
        actor=request.actor,
        reason=request.reason,
    )
    try:
        record = await run_blocking(handler.handle, cmd)
    except AppError as exc:
        raise_business_error(exc, conflict_keywords=_CONFLICT_KEYWORDS)
    return APIResponse(data=to_version_state_response(record))


@router.post(
    "/{strategy_id}/versions/{version}/approve",
    response_model=APIResponse[StrategyVersionStateResponse],
)
@inject
async def approve_strategy_review(
    strategy_id: str,
    version: int,
    request: GovernanceDecisionRequest,
    handler: Annotated[ApproveReviewHandler, FromComponent()],
) -> APIResponse[StrategyVersionStateResponse]:
    """审批策略版本."""
    cmd = ApproveReviewCommand(
        strategy_id=strategy_id,
        version=version,
        actor=request.actor,
        reason=request.reason,
    )
    try:
        record = await run_blocking(handler.handle, cmd)
    except AppError as exc:
        raise_business_error(exc, conflict_keywords=_CONFLICT_KEYWORDS)
    return APIResponse(data=to_version_state_response(record))


@router.post(
    "/{strategy_id}/versions/{version}/reject",
    response_model=APIResponse[StrategyVersionStateResponse],
)
@inject
async def reject_strategy_review(
    strategy_id: str,
    version: int,
    request: GovernanceDecisionRequest,
    handler: Annotated[RejectReviewHandler, FromComponent()],
) -> APIResponse[StrategyVersionStateResponse]:
    """驳回策略版本（驳回后只能 clone 新 draft）."""
    cmd = RejectReviewCommand(
        strategy_id=strategy_id,
        version=version,
        actor=request.actor,
        reason=request.reason,
    )
    try:
        record = await run_blocking(handler.handle, cmd)
    except AppError as exc:
        raise_business_error(exc, conflict_keywords=_CONFLICT_KEYWORDS)
    return APIResponse(data=to_version_state_response(record))


@router.post(
    "/{strategy_id}/versions/{version}/deprecate",
    response_model=APIResponse[StrategyVersionStateResponse],
)
@inject
async def deprecate_strategy_version(
    strategy_id: str,
    version: int,
    request: GovernanceDecisionRequest,
    handler: Annotated[DeprecateStrategyHandler, FromComponent()],
) -> APIResponse[StrategyVersionStateResponse]:
    """弃用已发布版本（弃用后不可再激活）."""
    cmd = DeprecateStrategyCommand(
        strategy_id=strategy_id,
        version=version,
        actor=request.actor,
        reason=request.reason,
    )
    try:
        record = await run_blocking(handler.handle, cmd)
    except AppError as exc:
        raise_business_error(exc, conflict_keywords=_CONFLICT_KEYWORDS)
    return APIResponse(data=to_version_state_response(record))


@router.post(
    "/{strategy_id}/versions/{version}/reactivate",
    response_model=APIResponse[StrategyActivePointerResponse],
)
@inject
async def reactivate_strategy_version(
    strategy_id: str,
    version: int,
    request: ReactivateStrategyRequest,
    handler: Annotated[ReactivateStrategyHandler, FromComponent()],
) -> APIResponse[StrategyActivePointerResponse]:
    """重新激活已发布版本（乐观指针 CAS，要求 expected_pointer_revision）."""
    cmd = ReactivateStrategyCommand(
        strategy_id=strategy_id,
        version=version,
        actor=request.actor,
        reason=request.reason,
        confirmation=request.confirmation,
        impact_summary=request.impact_summary,
        expected_pointer_revision=request.expected_pointer_revision,
    )
    try:
        pointer = await run_blocking(handler.handle, cmd)
    except AppError as exc:
        _raise_reactivate_error(exc)
    return APIResponse(data=to_active_pointer_response(pointer))


@router.post(
    "/{strategy_id}/versions/{version}/publish",
    response_model=APIResponse[StrategyActivePointerResponse],
)
@inject
async def publish_strategy_version(
    strategy_id: str,
    version: int,
    request: PublishStrategyVersionRequest,
    handler: Annotated[PublishStrategyVersionHandler, FromComponent()],
) -> APIResponse[StrategyActivePointerResponse]:
    """证据门控发布（经 StrategyPromotionProcess 验证 review packet hard gates）."""
    cmd = PublishStrategyVersionCommand(
        strategy_id=strategy_id,
        version=version,
        bundle_hash=request.bundle_hash,
        actor=request.actor,
        reason=request.reason,
    )
    try:
        pointer = await run_blocking(handler.handle, cmd)
    except AppError as exc:
        _raise_publish_error(exc)
    return APIResponse(data=to_active_pointer_response(pointer))


def to_validation_response(
    info: StrategySpecValidationInfo,
) -> StrategySpecValidationResponse:
    """将 candidate spec 校验 read model 转为 API 响应."""
    return StrategySpecValidationResponse(
        strategy_id=info.strategy_id,
        version=info.version,
        canonical_hash=info.canonical_hash,
        base_spec_hash=info.base_spec_hash,
        changed=info.changed,
        valid=info.valid,
        errors=list(info.errors),
    )


def to_diff_response(
    info: StrategyVersionDiffInfo,
) -> StrategyVersionDiffResponse:
    """将 version diff read model 转为 API 响应."""
    return StrategyVersionDiffResponse(
        strategy_id=info.strategy_id,
        version=info.version,
        parent_version=info.parent_version,
        base_spec_hash=info.base_spec_hash,
        target_spec_hash=info.target_spec_hash,
        changed=info.changed,
        changes=[
            SpecChangeResponse(
                path=change.path,
                op=change.op,
                old=change.old_value,
                new=change.new_value,
            )
            for change in info.changes
        ],
    )


@router.post(
    "/{strategy_id}/versions/{version}/validate",
    response_model=APIResponse[StrategySpecValidationResponse],
)
@inject
async def validate_strategy_version(
    strategy_id: str,
    version: int,
    request: StrategySpecValidateRequest,
    facade: Annotated[StrategyQueryFacade, FromComponent()],
) -> APIResponse[StrategySpecValidationResponse]:
    """校验 candidate spec_json（pre-save），返回 canonical hash + 合法性 + 变更检测."""
    info = await run_blocking(
        facade.validate_spec, strategy_id, version, request.spec_json
    )
    if info is None:
        raise NotFoundError(f"Strategy version not found: {strategy_id} v{version}")
    return APIResponse(data=to_validation_response(info))


@router.get(
    "/{strategy_id}/versions/{version}/diff",
    response_model=APIResponse[StrategyVersionDiffResponse],
)
@inject
async def diff_strategy_version(
    strategy_id: str,
    version: int,
    facade: Annotated[StrategyQueryFacade, FromComponent()],
) -> APIResponse[StrategyVersionDiffResponse]:
    """返回 version v 相对 parent_version 的 canonical spec 字段级 diff."""
    info = await run_blocking(facade.diff_version, strategy_id, version)
    if info is None:
        raise NotFoundError(f"Strategy version not found: {strategy_id} v{version}")
    return APIResponse(data=to_diff_response(info))
