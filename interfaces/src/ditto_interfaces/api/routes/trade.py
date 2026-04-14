"""
交易闭环 API 路由.

端点:
- GET    /trade/intents                       列出交易意图
- PUT    /trade/intents/{id}/status           更新意图状态
- POST   /trade/fills                          录入成交
- GET    /trade/fills                          列出成交记录
- GET    /trade/positions                      查询持仓快照
- GET    /trade/pnl                            盈亏汇总
- GET    /trade/signals/latest                 最新信号
- GET    /trade/signals/{strategy_id}/intents  信号意图明细
- GET    /trade/comparison                     回测 vs 实际对比
"""

from __future__ import annotations

import asyncio
from typing import Annotated, Never

from dishka import FromComponent
from dishka.integrations.fastapi import inject
from ditto_app.command.trade import (
    RecordFillCommand,
    RecordFillHandler,
    UpdateIntentStatusCommand,
    UpdateIntentStatusHandler,
)
from ditto_app.execution_dto import (
    ActualPositionSnapshot,
    ManualExecutionFill,
    TradeIntent,
)
from ditto_app.query.comparison import ComparisonMetrics, ComparisonQueryFacade
from ditto_app.query.portfolio_actual import PnlSummary, PortfolioActualQueryFacade
from ditto_app.query.signal import SignalQueryFacade
from ditto_app.query.trade import TradeQueryFacade
from fastapi import APIRouter, Depends, Query

from ditto_interfaces.api.deps import pagination_params
from ditto_interfaces.api.errors import BadRequestError, ConflictError, NotFoundError
from ditto_interfaces.models.common import (
    APIResponse,
    PaginationRequest,
    PaginationResponse,
)
from ditto_interfaces.models.trade import (
    ComparisonMetricsResponse,
    FillResponse,
    PnlSummaryResponse,
    PositionSnapshotResponse,
    RecordFillRequest,
    TradeIntentResponse,
    UpdateIntentStatusRequest,
)

router = APIRouter(prefix="/trade", tags=["trade"])


def _raise_trade_error(exc: ValueError) -> Never:
    """将 Trade 业务 ValueError 映射为对应的 APIError 并抛出."""
    msg = str(exc).lower()
    if "not found" in msg:
        raise NotFoundError(str(exc)) from exc
    if "transition" in msg:
        raise ConflictError(str(exc)) from exc
    raise BadRequestError(str(exc)) from exc


# ---------------------------------------------------------------------------
# Response Mappers (DTO → API Response)
# ---------------------------------------------------------------------------


def to_intent_response(dto: TradeIntent) -> TradeIntentResponse:
    """将 TradeIntent DTO 转为 API 响应."""
    return TradeIntentResponse(
        intent_id=dto.intent_id,
        strategy_id=dto.strategy_id,
        signal_date=dto.signal_date,
        instrument_id=dto.instrument_id,
        direction=dto.direction,
        target_weight=dto.target_weight,
        current_weight=dto.current_weight,
        delta_weight=dto.delta_weight,
        quantity=dto.quantity,
        status=dto.status,
    )


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


def to_position_response(dto: ActualPositionSnapshot) -> PositionSnapshotResponse:
    """将 ActualPositionSnapshot DTO 转为 API 响应."""
    return PositionSnapshotResponse(
        snapshot_id=dto.snapshot_id,
        strategy_id=dto.strategy_id,
        snapshot_date=dto.snapshot_date,
        instrument_id=dto.instrument_id,
        quantity=dto.quantity,
        available_quantity=dto.available_quantity,
        average_cost=dto.average_cost,
        market_value=dto.market_value,
        unrealized_pnl=dto.unrealized_pnl,
        realized_pnl=dto.realized_pnl,
        total_fees=dto.total_fees,
    )


def to_pnl_response(summary: PnlSummary) -> PnlSummaryResponse:
    """将 PnlSummary 转为 API 响应."""
    return PnlSummaryResponse(
        total_realized_pnl=summary.total_realized_pnl,
        total_unrealized_pnl=summary.total_unrealized_pnl,
        total_fees=summary.total_fees,
        net_pnl=summary.net_pnl,
    )


def to_comparison_response(metrics: ComparisonMetrics) -> ComparisonMetricsResponse:
    """将 ComparisonMetrics 转为 API 响应."""
    return ComparisonMetricsResponse(
        backtest_return=metrics.backtest_return,
        actual_return=metrics.actual_return,
        return_diff=metrics.return_diff,
        return_diff_bps=metrics.return_diff_bps,
        backtest_sharpe=metrics.backtest_sharpe,
        actual_sharpe=metrics.actual_sharpe,
        backtest_total_cost=metrics.backtest_total_cost,
        actual_total_cost=metrics.actual_total_cost,
        cost_drag_bps=metrics.cost_drag_bps,
        nav_correlation=metrics.nav_correlation,
        max_nav_diff_bps=metrics.max_nav_diff_bps,
        avg_daily_tracking_error_bps=metrics.avg_daily_tracking_error_bps,
    )


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
    pagination: PaginationRequest = Depends(pagination_params),
) -> APIResponse[list[TradeIntentResponse]]:
    """列出交易意图."""
    intents = await asyncio.to_thread(
        facade.list_intents,
        strategy_id=strategy_id,
        signal_date=signal_date,
        status=status,
    )
    all_intents = [to_intent_response(i) for i in intents]
    total = len(all_intents)
    page = all_intents[pagination.offset : pagination.offset + pagination.limit]
    return APIResponse(
        data=page,
        pagination=PaginationResponse(
            total=total, limit=pagination.limit, offset=pagination.offset
        ),
    )


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
    except ValueError as exc:
        _raise_trade_error(exc)
    return APIResponse(data=result)


# ---------------------------------------------------------------------------
# Fills
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
    except ValueError as exc:
        _raise_trade_error(exc)
    return APIResponse(data=to_fill_response(fill))


@router.get("/fills", response_model=APIResponse[list[FillResponse]])
@inject
async def list_fills(
    facade: Annotated[PortfolioActualQueryFacade, FromComponent()],
    strategy_id: str = Query(..., description="策略 ID"),
    start_date: str | None = Query(None, description="起始日期"),
    end_date: str | None = Query(None, description="结束日期"),
    pagination: PaginationRequest = Depends(pagination_params),
) -> APIResponse[list[FillResponse]]:
    """列出成交记录."""
    fills = await asyncio.to_thread(
        facade.get_fills,
        strategy_id=strategy_id,
        start_date=start_date,
        end_date=end_date,
    )
    all_fills = [to_fill_response(f) for f in fills]
    total = len(all_fills)
    page = all_fills[pagination.offset : pagination.offset + pagination.limit]
    return APIResponse(
        data=page,
        pagination=PaginationResponse(
            total=total, limit=pagination.limit, offset=pagination.offset
        ),
    )


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


@router.get("/pnl", response_model=APIResponse[PnlSummaryResponse])
@inject
async def compute_pnl(
    facade: Annotated[PortfolioActualQueryFacade, FromComponent()],
    strategy_id: str = Query(..., description="策略 ID"),
    snapshot_date: str = Query(..., description="快照日期"),
) -> APIResponse[PnlSummaryResponse]:
    """计算 P&L 汇总."""
    summary = await asyncio.to_thread(
        facade.compute_pnl,
        strategy_id=strategy_id,
        snapshot_date=snapshot_date,
    )
    return APIResponse(data=to_pnl_response(summary))


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
        raise NotFoundError(f"Backtest report not found for run_id={run_id}")
    return APIResponse(data=to_comparison_response(metrics))
