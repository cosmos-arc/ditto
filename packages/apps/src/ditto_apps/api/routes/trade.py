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
- GET    /trade/deviation                      信号-成交偏差报告
- GET    /trade/comparison                     回测 vs 实际对比
"""

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
from ditto_app.execution_dto import (
    ActualPositionSnapshot,
    ManualExecutionFill,
    TradeIntent,
)
from ditto_app.query.comparison import ComparisonQueryFacade
from ditto_app.query.comparison_math import ComparisonMetrics
from ditto_app.query.portfolio_actual import PnlSummary, PortfolioActualQueryFacade
from ditto_app.query.signal import SignalQueryFacade
from ditto_app.query.trade import TradeQueryFacade
from fastapi import APIRouter, Depends, Query

from ditto_apps.api.deps import paginate, pagination_params
from ditto_apps.api.errors import NotFoundError, raise_business_error
from ditto_apps.models.common import (
    APIResponse,
    PaginationRequest,
)
from ditto_apps.models.trade import (
    ComparisonMetricsResponse,
    DeviationResponse,
    FillResponse,
    PnlSummaryResponse,
    PositionSnapshotResponse,
    RecordFillRequest,
    SignalDeviationItem,
    TradeIntentResponse,
    UpdateIntentStatusRequest,
)

router = APIRouter(prefix="/trade", tags=["trade"])


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
    return paginate([to_intent_response(i) for i in intents], pagination)


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
        raise_business_error(exc, conflict_keywords=("transition",))
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
        raise_business_error(exc, conflict_keywords=("transition",))
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
    return paginate([to_fill_response(f) for f in fills], pagination)


# ---------------------------------------------------------------------------
# Positions
# ---------------------------------------------------------------------------


@router.get("/positions", response_model=APIResponse[list[PositionSnapshotResponse]])
@inject
async def list_positions(
    facade: Annotated[PortfolioActualQueryFacade, FromComponent()],
    strategy_id: str = Query(..., description="策略 ID"),
    snapshot_date: str | None = Query(None, description="快照日期"),
    pagination: PaginationRequest = Depends(pagination_params),
) -> APIResponse[list[PositionSnapshotResponse]]:
    """列出实际持仓."""
    snapshots = await asyncio.to_thread(
        facade.get_position_history,
        strategy_id=strategy_id,
        snapshot_date=snapshot_date,
    )
    return paginate([to_position_response(s) for s in snapshots], pagination)


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
    pagination: PaginationRequest = Depends(pagination_params),
) -> APIResponse[list[TradeIntentResponse]]:
    """获取最新信号日期的交易意图."""
    intents = await asyncio.to_thread(
        facade.get_latest_intents,
        strategy_id=strategy_id,
    )
    return paginate([to_intent_response(i) for i in intents], pagination)


@router.get(
    "/signals/{signal_date}/intents",
    response_model=APIResponse[list[TradeIntentResponse]],
)
@inject
async def get_signal_intents(
    signal_date: str,
    facade: Annotated[SignalQueryFacade, FromComponent()],
    strategy_id: str = Query(..., description="策略 ID"),
    pagination: PaginationRequest = Depends(pagination_params),
) -> APIResponse[list[TradeIntentResponse]]:
    """获取指定信号日期的交易意图."""
    intents = await asyncio.to_thread(
        facade.get_intents_by_date,
        strategy_id=strategy_id,
        signal_date=signal_date,
    )
    return paginate([to_intent_response(i) for i in intents], pagination)


# ---------------------------------------------------------------------------
# Deviation
# ---------------------------------------------------------------------------


@router.get("/deviation", response_model=APIResponse[DeviationResponse])
@inject
async def get_deviation(
    trade_facade: Annotated[TradeQueryFacade, FromComponent()],
    portfolio_facade: Annotated[PortfolioActualQueryFacade, FromComponent()],
    strategy_id: str = Query(..., description="策略 ID"),
    signal_date: str = Query(..., description="信号日期"),
) -> APIResponse[DeviationResponse]:
    """信号-成交偏差报告."""
    intents, fills = await asyncio.gather(
        asyncio.to_thread(
            trade_facade.list_intents,
            strategy_id=strategy_id,
            signal_date=signal_date,
        ),
        asyncio.to_thread(
            portfolio_facade.get_fills,
            strategy_id=strategy_id,
            start_date=signal_date,
            end_date=signal_date,
        ),
    )

    fill_qty_by_instrument: dict[int, int] = {}
    for fill in fills:
        iid = fill.instrument_id
        fill_qty_by_instrument[iid] = fill_qty_by_instrument.get(iid, 0) + fill.quantity

    items: list[SignalDeviationItem] = []
    filled_count = 0
    for intent in intents:
        actual_qty = fill_qty_by_instrument.get(intent.instrument_id, 0)
        has_fill = actual_qty > 0
        if has_fill:
            filled_count += 1

        items.append(
            SignalDeviationItem(
                instrument_id=intent.instrument_id,
                signal_action=intent.direction,
                signal_weight=intent.target_weight,
                actual_weight=intent.target_weight if has_fill else None,
                deviation_bps=0.0 if has_fill else None,
                fill_status="filled" if has_fill else "unfilled",
            )
        )

    return APIResponse(
        data=DeviationResponse(
            strategy_id=strategy_id,
            signal_date=signal_date,
            total_signals=len(intents),
            filled=filled_count,
            unfilled=len(intents) - filled_count,
            items=items,
        )
    )


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
