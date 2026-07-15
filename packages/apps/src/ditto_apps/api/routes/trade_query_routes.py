"""
交易查询路由 — 意图/成交/持仓/盈亏/信号/偏差/对比.

端点:
- GET  /trade/intents                        列出交易意图
- GET  /trade/fills                          列出成交记录
- GET  /trade/positions                      查询持仓快照
- GET  /trade/pnl                            盈亏汇总
- GET  /trade/signals/latest                 最新信号
- GET  /trade/signals/{strategy_id}/intents  信号意图明细
- GET  /trade/deviation                      信号-成交偏差报告
- GET  /trade/comparison                     回测 vs 实际对比
"""

from __future__ import annotations

import asyncio
from typing import Annotated

from dishka import FromComponent
from dishka.integrations.fastapi import inject
from ditto_application.execution_dto import (
    ActualPositionSnapshot,
    TradeIntent,
)
from ditto_application.queries.account import AccountBaselineQuery
from ditto_application.queries.comparison import ComparisonQueryFacade
from ditto_application.queries.comparison_math import ComparisonMetrics
from ditto_application.queries.daily_decision import (
    DailyDecisionQueryFacade,
    DailyDecisionReport,
)
from ditto_application.queries.deviation import SignalDeviationReport
from ditto_application.queries.portfolio_actual import (
    PnlSummary,
    PortfolioActualQueryFacade,
)
from ditto_application.queries.signal import SignalQueryFacade
from ditto_application.queries.trade import TradeQueryFacade
from fastapi import APIRouter, Depends, Query

from ditto_apps.api.deps import paginate, pagination_params
from ditto_apps.api.errors import NotFoundError
from ditto_apps.models.common import (
    APIResponse,
    PaginationRequest,
)
from ditto_apps.models.trade import (
    AccountBaselineResponse,
    ComparisonMetricsResponse,
    DailyDecisionReadinessResponse,
    DailyDecisionReportResponse,
    DeviationResponse,
    FillResponse,
    PnlSummaryResponse,
    PositionSnapshotResponse,
    SignalDeviationItem,
    TradeIntentResponse,
)

router = APIRouter()


@router.get(
    "/account-baseline",
    response_model=APIResponse[AccountBaselineResponse | None],
)
@inject
async def get_account_baseline(
    query: Annotated[AccountBaselineQuery, FromComponent()],
    account_id: str = Query(..., description="账户 ID"),
    strategy_id: str = Query(..., description="策略 ID"),
    signal_date: str = Query(..., description="信号日期"),
) -> APIResponse[AccountBaselineResponse | None]:
    """返回不晚于信号日的最新账户基线及同日持仓。"""
    result = await asyncio.to_thread(
        query.get_latest,
        account_id=account_id,
        strategy_id=strategy_id,
        signal_date=signal_date,
    )
    if result is None:
        return APIResponse(data=None)
    account = result.account
    return APIResponse(
        data=AccountBaselineResponse(
            snapshot_id=account.snapshot_id,
            sleeve_id=account.run_id,
            account_id=account.account_id,
            strategy_id=account.strategy_id,
            snapshot_date=account.snapshot_date,
            cash_available=account.cash_available,
            cash_settled=account.cash_settled,
            cash_frozen=account.cash_frozen,
            total_value=account.total_value,
            nav=account.nav,
            exposure=account.exposure,
            positions=[
                PositionSnapshotResponse(
                    snapshot_id=item.snapshot_id,
                    strategy_id=item.strategy_id,
                    snapshot_date=item.snapshot_date,
                    instrument_id=item.instrument_id,
                    quantity=item.quantity,
                    available_quantity=item.available_quantity,
                    average_cost=item.average_cost,
                    market_value=item.market_value,
                    unrealized_pnl=item.unrealized_pnl,
                    realized_pnl=item.realized_pnl,
                    total_fees=item.total_fees,
                )
                for item in result.positions
            ],
        )
    )


# ---------------------------------------------------------------------------
# Response Mappers
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


def to_deviation_response(report: SignalDeviationReport) -> DeviationResponse:
    """将 SignalDeviationReport 转为 API 响应."""
    return DeviationResponse(
        strategy_id=report.strategy_id,
        signal_date=report.signal_date,
        total_signals=report.total_signals,
        filled=report.filled,
        unfilled=report.unfilled,
        items=[
            SignalDeviationItem(
                instrument_id=item.instrument_id,
                signal_action=item.signal_action,
                signal_weight=item.signal_weight,
                actual_weight=item.actual_weight,
                deviation_bps=item.deviation_bps,
                fill_status=item.fill_status,
            )
            for item in report.items
        ],
    )


def to_daily_decision_response(
    report: DailyDecisionReport,
) -> DailyDecisionReportResponse:
    """将 DailyDecisionReport 转为 API 响应."""
    return DailyDecisionReportResponse(
        strategy_id=report.strategy_id,
        trade_date=report.trade_date,
        readiness=DailyDecisionReadinessResponse(
            status=report.readiness_status,
            reasons=list(report.readiness_reasons),
        ),
        signal_intents=[to_intent_response(intent) for intent in report.signal_intents],
        positions=[to_position_response(position) for position in report.positions],
        deviation=(
            to_deviation_response(report.deviation)
            if report.deviation is not None
            else None
        ),
        pnl=to_pnl_response(report.pnl) if report.pnl is not None else None,
    )


# ---------------------------------------------------------------------------
# Re-export fill mapper from command routes (shared between command & query)
# ---------------------------------------------------------------------------

from ditto_apps.api.routes.trade_command_routes import (  # noqa: E402
    to_fill_response,
)

# ---------------------------------------------------------------------------
# Daily Decision
# ---------------------------------------------------------------------------


@router.get(
    "/daily-decision",
    response_model=APIResponse[DailyDecisionReportResponse],
)
@inject
async def get_daily_decision(
    facade: Annotated[DailyDecisionQueryFacade, FromComponent()],
    strategy_id: str = Query(..., description="策略 ID"),
    trade_date: str | None = Query(None, description="交易/信号日期"),
) -> APIResponse[DailyDecisionReportResponse]:
    """获取每日决策驾驶舱报告."""
    report = await asyncio.to_thread(
        facade.get_report,
        strategy_id=strategy_id,
        trade_date=trade_date,
    )
    return APIResponse(data=to_daily_decision_response(report))


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


# ---------------------------------------------------------------------------
# Fills
# ---------------------------------------------------------------------------


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
