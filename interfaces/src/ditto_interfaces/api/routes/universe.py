"""
Universe API 路由.

端点:
- GET    /universes                           列出 Universe
- GET    /universes/{id}                      获取 Universe 详情
- GET    /universes/{id}/members              查询成分列表
- POST   /universes                           创建自定义 Universe
- PUT    /universes/{id}                      更新 Universe
- DELETE /universes/{id}                      删除 Universe
"""

from __future__ import annotations

import asyncio
from typing import Annotated

from dishka import FromComponent
from dishka.integrations.fastapi import inject
from ditto_app.command.universe import (
    CreateCustomUniverseCommand,
    CreateCustomUniverseHandler,
    DeleteCustomUniverseCommand,
    DeleteCustomUniverseHandler,
    UpdateCustomUniverseCommand,
    UpdateCustomUniverseHandler,
)
from ditto_app.query.universe import UniverseQueryFacade
from fastapi import APIRouter, Depends, Query

from ditto_interfaces.api.deps import paginate, pagination_params
from ditto_interfaces.api.errors import BadRequestError, ForbiddenError, NotFoundError
from ditto_interfaces.models.common import (
    APIResponse,
    PaginationRequest,
)
from ditto_interfaces.models.universe import (
    CreateUniverseRequest,
    MemberResponse,
    UniverseResponse,
    UpdateUniverseRequest,
    to_universe_response,
)

router = APIRouter(prefix="/universes", tags=["universes"])


@router.get("", response_model=APIResponse[list[UniverseResponse]])
@inject
async def list_universes(
    facade: Annotated[UniverseQueryFacade, FromComponent()],
    pagination: PaginationRequest = Depends(pagination_params),
    universe_type: str | None = Query(None, description="类型过滤"),
) -> APIResponse[list[UniverseResponse]]:
    """列出所有 Universe."""
    rows = await asyncio.to_thread(facade.list_universes, universe_type)
    return paginate([to_universe_response(r) for r in rows], pagination)


@router.get("/{universe_id}", response_model=APIResponse[UniverseResponse])
@inject
async def get_universe(
    universe_id: str,
    facade: Annotated[UniverseQueryFacade, FromComponent()],
) -> APIResponse[UniverseResponse]:
    """获取 Universe 详情."""
    row = await asyncio.to_thread(facade.get_universe_detail, universe_id)
    if row is None:
        raise NotFoundError(f"Universe not found: {universe_id}")
    return APIResponse(data=to_universe_response(row))


@router.get("/{universe_id}/members", response_model=APIResponse[list[MemberResponse]])
@inject
async def get_members(
    universe_id: str,
    facade: Annotated[UniverseQueryFacade, FromComponent()],
    asof: str | None = Query(None, description="PIT 日期"),
) -> APIResponse[list[MemberResponse]]:
    """获取 Universe 成分股."""
    ids = await asyncio.to_thread(facade.get_members, universe_id, asof)
    return APIResponse(data=[MemberResponse(instrument_id=iid) for iid in ids])


@router.post("", status_code=201, response_model=APIResponse[UniverseResponse])
@inject
async def create_universe(
    body: CreateUniverseRequest,
    handler: Annotated[CreateCustomUniverseHandler, FromComponent()],
) -> APIResponse[UniverseResponse]:
    """创建自定义 Universe."""
    cmd = CreateCustomUniverseCommand(
        universe_id=body.universe_id,
        name=body.name,
        description=body.description,
    )
    try:
        row = await asyncio.to_thread(handler.handle, cmd)
    except ValueError as exc:
        raise BadRequestError(str(exc)) from exc
    return APIResponse(data=to_universe_response(row))


@router.put("/{universe_id}", response_model=APIResponse[UniverseResponse])
@inject
async def update_universe(
    universe_id: str,
    body: UpdateUniverseRequest,
    handler: Annotated[UpdateCustomUniverseHandler, FromComponent()],
) -> APIResponse[UniverseResponse]:
    """更新自定义 Universe."""
    cmd = UpdateCustomUniverseCommand(
        universe_id=universe_id,
        name=body.name,
        description=body.description,
        members=body.members,
        effective_date=body.effective_date,
    )
    try:
        row = await asyncio.to_thread(handler.handle, cmd)
    except PermissionError as exc:
        raise ForbiddenError(str(exc)) from exc
    except ValueError as exc:
        raise NotFoundError(str(exc)) from exc
    return APIResponse(data=to_universe_response(row))


@router.delete("/{universe_id}", response_model=APIResponse[bool])
@inject
async def delete_universe(
    universe_id: str,
    handler: Annotated[DeleteCustomUniverseHandler, FromComponent()],
) -> APIResponse[bool]:
    """删除自定义 Universe（预设不可删）."""
    cmd = DeleteCustomUniverseCommand(universe_id=universe_id)
    try:
        result = await asyncio.to_thread(handler.handle, cmd)
    except ValueError as exc:
        msg = str(exc)
        if "preset" in msg:
            raise ForbiddenError(msg) from exc
        raise NotFoundError(msg) from exc
    return APIResponse(data=result)
