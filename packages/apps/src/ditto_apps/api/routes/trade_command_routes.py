"""
交易命令路由 — 更新意图状态 / 录入成交.

端点:
- PUT   /trade/intents/{id}/status    更新意图状态
- POST  /trade/fills                   录入成交
"""

from __future__ import annotations

import asyncio
from typing import Annotated

from dishka import FromComponent
from dishka.integrations.fastapi import inject
from ditto_application.commands.trade import (
    RecordFillCommand,
    RecordFillHandler,
    UpdateIntentStatusCommand,
    UpdateIntentStatusHandler,
)
from ditto_application.exceptions import AppError
from ditto_application.execution_dto import ManualExecutionFill
from fastapi import APIRouter

from ditto_apps.api.errors import raise_business_error
from ditto_apps.models.common import APIResponse
from ditto_apps.models.trade import (
    FillResponse,
    RecordFillRequest,
    UpdateIntentStatusRequest,
)

router = APIRouter()


# ---------------------------------------------------------------------------
# Response Mapper
# ---------------------------------------------------------------------------


def to_fill_response(dto: ManualExecutionFill) -> FillResponse:
    """将 ManualExecutionFill DTO 转为 API 响应."""
    return FillResponse(
        fill_id=dto.fill_id,
        intent_id=dto.intent_id,
        strategy_id=dto.strategy_id,
        trade_date=dto.trade_date,
        instrument_id=dto.instrument_id,
        direction=dto.direction,
        quantity=dto.quantity,
        fill_price=dto.fill_price,
        fee=dto.fee,
        slippage=dto.slippage,
        notes=dto.notes,
        settlement_date=dto.settlement_date,
    )


# ---------------------------------------------------------------------------
# Update Intent Status
# ---------------------------------------------------------------------------


@router.put("/intents/{intent_id}/status", response_model=APIResponse[bool])
@inject
async def update_intent_status(
    intent_id: str,
    request: UpdateIntentStatusRequest,
    handler: Annotated[UpdateIntentStatusHandler, FromComponent()],
) -> APIResponse[bool]:
    """更新交易意图状态."""
    cmd = UpdateIntentStatusCommand(
        intent_id=intent_id,
        status=request.status,
    )
    try:
        result = await asyncio.to_thread(handler.handle, cmd)
    except (AppError, ValueError) as exc:
        raise_business_error(exc, conflict_keywords=("transition",))
    return APIResponse(data=result)


# ---------------------------------------------------------------------------
# Record Fill
# ---------------------------------------------------------------------------


@router.post("/fills", response_model=APIResponse[FillResponse])
@inject
async def record_fill(
    request: RecordFillRequest,
    handler: Annotated[RecordFillHandler, FromComponent()],
) -> APIResponse[FillResponse]:
    """录入人工成交."""
    cmd = RecordFillCommand(
        fill_id=request.fill_id,
        intent_id=request.intent_id,
        strategy_id=request.strategy_id,
        trade_date=request.trade_date,
        instrument_id=request.instrument_id,
        direction=request.direction,
        quantity=request.quantity,
        fill_price=request.fill_price,
        fee=request.fee,
        slippage=request.slippage,
        notes=request.notes,
    )
    try:
        fill = await asyncio.to_thread(handler.handle, cmd)
    except (AppError, ValueError) as exc:
        raise_business_error(exc, conflict_keywords=("transition",))
    return APIResponse(data=to_fill_response(fill))
