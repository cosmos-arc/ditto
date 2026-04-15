"""
策略 API 路由.

端点:
- POST   /strategies                          创建策略
- GET    /strategies                          列出策略
- GET    /strategies/{id}                     获取策略详情
- PUT    /strategies/{id}                     更新策略
- POST   /strategies/{id}/publish             发布策略
"""

from __future__ import annotations

import asyncio
from typing import Annotated, Never

from dishka import FromComponent
from dishka.integrations.fastapi import inject
from ditto_app.command.strategy import (
    CreateStrategyCommand,
    CreateStrategyHandler,
    PublishStrategyCommand,
    PublishStrategyHandler,
    UpdateStrategyCommand,
    UpdateStrategyHandler,
)
from ditto_app.contracts import StrategySpecInfo
from ditto_app.query.strategy import StrategyQueryFacade
from fastapi import APIRouter, Depends

from ditto_interfaces.api.deps import paginate, pagination_params
from ditto_interfaces.api.errors import BadRequestError, ConflictError, NotFoundError
from ditto_interfaces.models.common import (
    APIResponse,
    PaginationRequest,
)
from ditto_interfaces.models.strategy import (
    CreateStrategyRequest,
    PublishStrategyRequest,
    StrategyResponse,
    UpdateStrategyRequest,
)

router = APIRouter(prefix="/strategies", tags=["strategies"])


def _raise_strategy_error(exc: ValueError) -> Never:
    """将 Strategy handler 的 ValueError 映射为对应的 APIError 并抛出."""
    msg = str(exc)
    if "not found" in msg.lower():
        raise NotFoundError(msg) from exc
    if "conflict" in msg.lower():
        raise ConflictError(msg) from exc
    raise BadRequestError(msg) from exc


def to_strategy_response(info: StrategySpecInfo) -> StrategyResponse:
    """将 App StrategySpecInfo 转为 API 响应."""
    return StrategyResponse(
        strategy_id=info.strategy_id,
        name=info.name,
        spec_json=dict(info.spec_json),
        version=info.version,
        status=info.status,
        created_at=info.created_at,
        updated_at=info.updated_at,
        tags=list(info.tags),
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
    info = await asyncio.to_thread(handler.handle, cmd)
    return APIResponse(data=to_strategy_response(info))


@router.get("", response_model=APIResponse[list[StrategyResponse]])
@inject
async def list_strategies(
    facade: Annotated[StrategyQueryFacade, FromComponent()],
    pagination: PaginationRequest = Depends(pagination_params),
) -> APIResponse[list[StrategyResponse]]:
    """列出策略."""
    specs = await asyncio.to_thread(facade.list_specs)
    return paginate([to_strategy_response(s) for s in specs], pagination)


@router.get("/{strategy_id}", response_model=APIResponse[StrategyResponse])
@inject
async def get_strategy(
    strategy_id: str,
    facade: Annotated[StrategyQueryFacade, FromComponent()],
) -> APIResponse[StrategyResponse]:
    """获取策略详情."""
    info = await asyncio.to_thread(facade.get_spec, strategy_id)
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
        info = await asyncio.to_thread(handler.handle, cmd)
    except ValueError as exc:
        _raise_strategy_error(exc)
    return APIResponse(data=to_strategy_response(info))


@router.post("/{strategy_id}/publish", response_model=APIResponse[bool])
@inject
async def publish_strategy(
    strategy_id: str,
    request: PublishStrategyRequest,
    handler: Annotated[PublishStrategyHandler, FromComponent()],
) -> APIResponse[bool]:
    """发布策略."""
    cmd = PublishStrategyCommand(
        strategy_id=strategy_id,
        version=request.version,
    )
    try:
        result = await asyncio.to_thread(handler.handle, cmd)
    except ValueError as exc:
        _raise_strategy_error(exc)
    return APIResponse(data=result)
