"""交易闭环 API 路由."""

from __future__ import annotations

import asyncio
from typing import Annotated

from dishka import FromComponent
from dishka.integrations.fastapi import inject
from ditto_app.command.trade import (
    RecordFillCommand,
    RecordFillHandler,
    UpdateIntentStatusCommand,
    UpdateIntentStatusHandler,
)
from ditto_app.query.comparison import ComparisonQueryFacade
from ditto_app.query.portfolio_actual import PortfolioActualQueryFacade
from ditto_app.query.signal import SignalQueryFacade  # noqa: RUF100
from ditto_app.query.trade import TradeQueryFacade
from fastapi import APIRouter, HTTPException, Query

from ditto_interfaces.models.common import APIResponse
from ditto_interfaces.models.trade import (
    ComparisonMetricsResponse,
    FillResponse,
    PnlSummaryResponse,
    PositionSnapshotResponse,
    RecordFillRequest,
    TradeIntentResponse,
    UpdateIntentStatusRequest,
    to_comparison_response,
    to_fill_response,
    to_intent_response,
    to_pnl_response,
    to_position_response,
)

router = APIRouter(prefix="/trade", tags=["trade"])


# ---------------------------------------------------------------------------
# Trade Intents
# ---------------------------------------------------------------------------


@router.get("/intents", response_model=APIResponse[list[TradeIntentResponse]])
@inject
async def list_intents(
    facade: Annotated[TradeQueryFacade, FromComponent()],
    strategy_id: str = Query(..., description="策略 ID"),
    signal_date: str | None = Query(None, description="信号日期"),
    status: str | None = Query(None, description="状态过滤"),
) -> APIResponse[list[TradeIntentResponse]]:
    """列出交易意图."""
    intents = await asyncio.to_thread(
        facade.list_intents,
        strategy_id=strategy_id,
        signal_date=signal_date,
        status=status,
    )
    return APIResponse(data=[to_intent_response(i) for i in intents])


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
    result = await asyncio.to_thread(handler.handle, cmd)
    return APIResponse(data=result)


# ---------------------------------------------------------------------------
# Fills
# ---------------------------------------------------------------------------


@router.post("/fills", response_model=FillResponse)
@inject
async def record_fill(
    request: RecordFillRequest,
    handler: Annotated[RecordFillHandler, FromComponent()],
) -> FillResponse:
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
    fill = await asyncio.to_thread(handler.handle, cmd)
    return to_fill_response(fill)


@router.get("/fills", response_model=APIResponse[list[FillResponse]])
@inject
async def list_fills(
    facade: Annotated[PortfolioActualQueryFacade, FromComponent()],
    strategy_id: str = Query(..., description="策略 ID"),
    start_date: str | None = Query(None, description="起始日期"),
    end_date: str | None = Query(None, description="结束日期"),
) -> APIResponse[list[FillResponse]]:
    """列出成交记录."""
    fills = await asyncio.to_thread(
        facade.get_fills,
        strategy_id=strategy_id,
        start_date=start_date,
        end_date=end_date,
    )
    return APIResponse(data=[to_fill_response(f) for f in fills])


# ---------------------------------------------------------------------------
# Positions
# ---------------------------------------------------------------------------


@router.get("/positions", response_model=APIResponse[list[PositionSnapshotResponse]])
@inject
async def list_positions(
    facade: Annotated[PortfolioActualQueryFacade, FromComponent()],
    strategy_id: str = Query(..., description="策略 ID"),
    snapshot_date: str | None = Query(None, description="快照日期"),
) -> APIResponse[list[PositionSnapshotResponse]]:
    """列出实际持仓."""
    snapshots = await asyncio.to_thread(
        facade.get_position_history,
        strategy_id=strategy_id,
        snapshot_date=snapshot_date,
    )
    return APIResponse(data=[to_position_response(s) for s in snapshots])


# ---------------------------------------------------------------------------
# P&L
# ---------------------------------------------------------------------------


@router.get("/pnl", response_model=PnlSummaryResponse)
@inject
async def compute_pnl(
    facade: Annotated[PortfolioActualQueryFacade, FromComponent()],
    strategy_id: str = Query(..., description="策略 ID"),
    snapshot_date: str = Query(..., description="快照日期"),
) -> PnlSummaryResponse:
    """计算 P&L 汇总."""
    summary = await asyncio.to_thread(
        facade.compute_pnl,
        strategy_id=strategy_id,
        snapshot_date=snapshot_date,
    )
    return to_pnl_response(summary)


# ---------------------------------------------------------------------------
# Signals
# ---------------------------------------------------------------------------


@router.get("/signals/latest", response_model=APIResponse[list[TradeIntentResponse]])
@inject
async def get_latest_signals(
    facade: Annotated[SignalQueryFacade, FromComponent()],
    strategy_id: str = Query(..., description="策略 ID"),
) -> APIResponse[list[TradeIntentResponse]]:
    """获取最新信号日期的交易意图."""
    intents = await asyncio.to_thread(
        facade.get_latest_intents,
        strategy_id=strategy_id,
    )
    return APIResponse(data=[to_intent_response(i) for i in intents])


@router.get(
    "/signals/{signal_date}/intents",
    response_model=APIResponse[list[TradeIntentResponse]],
)
@inject
async def get_signal_intents(
    signal_date: str,
    facade: Annotated[SignalQueryFacade, FromComponent()],
    strategy_id: str = Query(..., description="策略 ID"),
) -> APIResponse[list[TradeIntentResponse]]:
    """获取指定信号日期的交易意图."""
    intents = await asyncio.to_thread(
        facade.get_intents_by_date,
        strategy_id=strategy_id,
        signal_date=signal_date,
    )
    return APIResponse(data=[to_intent_response(i) for i in intents])


# ---------------------------------------------------------------------------
# Comparison
# ---------------------------------------------------------------------------


@router.get("/comparison", response_model=APIResponse[ComparisonMetricsResponse])
@inject
async def get_comparison(
    facade: Annotated[ComparisonQueryFacade, FromComponent()],
    strategy_id: str = Query(..., description="策略 ID"),
    run_id: str = Query(..., description="回测运行 ID"),
) -> APIResponse[ComparisonMetricsResponse]:
    """回测 vs 实际对比."""
    metrics = await asyncio.to_thread(
        facade.get_comparison,
        strategy_id=strategy_id,
        run_id=run_id,
    )
    if metrics is None:
        raise HTTPException(
            status_code=404,
            detail=f"Backtest report not found for run_id={run_id}",
        )
    return APIResponse(data=to_comparison_response(metrics))
