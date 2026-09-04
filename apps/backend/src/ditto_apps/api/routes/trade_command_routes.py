"""
Manual 命令路由 — 更新本地意图状态 / 录入人工成交.

端点:
- PUT   /manual/intents/{id}/status    更新本地意图状态
- POST  /manual/fills                   录入人工成交
"""

from __future__ import annotations

import asyncio
from typing import Annotated, Never

from dishka import FromComponent
from dishka.integrations.fastapi import inject
from ditto_application.commands.account import (
    ImportAccountBaselineCommand,
    ImportAccountBaselineHandler,
    PositionBaselineInput,
)
from ditto_application.commands.trade import (
    RecordFillCommand,
    RecordFillHandler,
    ReplaceFillCommand,
    ReplaceFillHandler,
    UpdateIntentStatusCommand,
    UpdateIntentStatusHandler,
    VoidFillCommand,
    VoidFillHandler,
)
from ditto_application.exceptions import (
    AppConflictError,
    AppError,
    AppNotFoundError,
)
from ditto_application.execution_dto import FillAdjustment, ManualExecutionFill
from fastapi import APIRouter

from ditto_apps.api.errors import ConflictError, NotFoundError, raise_business_error
from ditto_apps.models.common import APIResponse
from ditto_apps.models.trade import (
    AccountBaselineImportResponse,
    FillAdjustmentResponse,
    FillResponse,
    ImportAccountBaselineRequest,
    RecordFillRequest,
    ReplaceFillRequest,
    UpdateIntentStatusRequest,
    VoidFillRequest,
)

router = APIRouter()


@router.post(
    "/account-baseline",
    response_model=APIResponse[AccountBaselineImportResponse],
)
@inject
async def import_account_baseline(
    request: ImportAccountBaselineRequest,
    handler: Annotated[ImportAccountBaselineHandler, FromComponent()],
) -> APIResponse[AccountBaselineImportResponse]:
    """幂等导入账户与持仓期初基线。"""
    command = ImportAccountBaselineCommand(
        account_id=request.account_id,
        strategy_id=request.strategy_id,
        snapshot_date=request.snapshot_date,
        cash_available=request.cash_available,
        cash_settled=request.cash_settled,
        cash_frozen=request.cash_frozen,
        total_value=request.total_value,
        nav=request.nav,
        positions=tuple(
            PositionBaselineInput(**item.model_dump()) for item in request.positions
        ),
        replace_confirmed=request.replace_confirmed,
    )
    try:
        result = await asyncio.to_thread(handler.handle, command)
    except (AppError, ValueError) as exc:
        raise_business_error(exc, conflict_keywords=("differs",))
    return APIResponse(data=AccountBaselineImportResponse(**result.__dict__))


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


def to_fill_adjustment_response(dto: FillAdjustment) -> FillAdjustmentResponse:
    """将不可变成交修正 DTO 转为 API 响应。"""
    return FillAdjustmentResponse(**dto.__dict__)


def _raise_trade_command_error(exc: Exception) -> Never:
    """按应用层显式错误类型映射成交命令的 HTTP 语义。"""
    if isinstance(exc, AppNotFoundError):
        raise NotFoundError(str(exc)) from exc
    if isinstance(exc, AppConflictError):
        raise ConflictError(str(exc)) from exc
    raise_business_error(exc)


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
        if isinstance(exc, AppConflictError | AppNotFoundError):
            _raise_trade_command_error(exc)
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
        _raise_trade_command_error(exc)
    return APIResponse(data=to_fill_response(fill))


@router.post(
    "/fills/{fill_id}/void",
    response_model=APIResponse[FillAdjustmentResponse],
)
@inject
async def void_fill(
    fill_id: str,
    request: VoidFillRequest,
    handler: Annotated[VoidFillHandler, FromComponent()],
) -> APIResponse[FillAdjustmentResponse]:
    """追加作废事件；原始成交保持不可变。"""
    command = VoidFillCommand(
        adjustment_id=request.adjustment_id,
        fill_id=fill_id,
        reason=request.reason,
    )
    try:
        adjustment = await asyncio.to_thread(handler.handle, command)
    except (AppError, ValueError) as exc:
        _raise_trade_command_error(exc)
    return APIResponse(data=to_fill_adjustment_response(adjustment))


@router.post(
    "/fills/{fill_id}/replace",
    response_model=APIResponse[FillAdjustmentResponse],
)
@inject
async def replace_fill(
    fill_id: str,
    request: ReplaceFillRequest,
    handler: Annotated[ReplaceFillHandler, FromComponent()],
) -> APIResponse[FillAdjustmentResponse]:
    """追加替换成交及链接事件；原始成交保持不可变。"""
    command = ReplaceFillCommand(
        adjustment_id=request.adjustment_id,
        fill_id=fill_id,
        replacement_fill_id=request.replacement_fill_id,
        trade_date=request.trade_date,
        quantity=request.quantity,
        fill_price=request.fill_price,
        reason=request.reason,
        fee=request.fee,
        slippage=request.slippage,
        notes=request.notes,
    )
    try:
        adjustment = await asyncio.to_thread(handler.handle, command)
    except (AppError, ValueError) as exc:
        _raise_trade_command_error(exc)
    return APIResponse(data=to_fill_adjustment_response(adjustment))
