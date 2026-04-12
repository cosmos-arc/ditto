"""Universe API 路由."""

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
from fastapi import APIRouter, HTTPException, Query

from ditto_interfaces.models.common import APIResponse
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
    universe_type: str | None = Query(None, description="类型过滤"),
) -> APIResponse[list[UniverseResponse]]:
    """列出所有 Universe."""
    rows = await asyncio.to_thread(facade.list_universes, universe_type)
    return APIResponse(data=[to_universe_response(r) for r in rows])


@router.get("/{universe_id}", response_model=UniverseResponse)
@inject
async def get_universe(
    universe_id: str,
    facade: Annotated[UniverseQueryFacade, FromComponent()],
) -> UniverseResponse:
    """获取 Universe 详情."""
    row = await asyncio.to_thread(facade.get_universe_detail, universe_id)
    if row is None:
        raise HTTPException(
            status_code=404,
            detail=f"Universe not found: {universe_id}",
        )
    return to_universe_response(row)


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


@router.post("", status_code=201, response_model=UniverseResponse)
@inject
async def create_universe(
    body: CreateUniverseRequest,
    handler: Annotated[CreateCustomUniverseHandler, FromComponent()],
) -> UniverseResponse:
    """创建自定义 Universe."""
    cmd = CreateCustomUniverseCommand(
        universe_id=body.universe_id,
        name=body.name,
        description=body.description,
    )
    try:
        row = await asyncio.to_thread(handler.handle, cmd)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return to_universe_response(row)


@router.put("/{universe_id}", response_model=UniverseResponse)
@inject
async def update_universe(
    universe_id: str,
    body: UpdateUniverseRequest,
    handler: Annotated[UpdateCustomUniverseHandler, FromComponent()],
) -> UniverseResponse:
    """更新自定义 Universe."""
    cmd = UpdateCustomUniverseCommand(
        universe_id=universe_id,
        name=body.name,
        description=body.description,
    )
    try:
        row = await asyncio.to_thread(handler.handle, cmd)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return to_universe_response(row)


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
            raise HTTPException(status_code=403, detail=msg) from exc
        raise HTTPException(status_code=404, detail=msg) from exc
    return APIResponse(data=result)
