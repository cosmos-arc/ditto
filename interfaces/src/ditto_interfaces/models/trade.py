"""交易闭环 API 模型."""

from __future__ import annotations

from typing import Literal

from ditto_app.query.comparison import ComparisonMetrics
from ditto_app.query.portfolio_actual import PnlSummary
from ditto_app.types import ActualPositionSnapshot, ManualExecutionFill, TradeIntent
from pydantic import BaseModel, ConfigDict, Field


class RecordFillRequest(BaseModel):
    """录入成交请求."""

    fill_id: str = Field(description="成交唯一标识")
    intent_id: str = Field(description="关联交易意图 ID")
    strategy_id: str = Field(description="策略 ID")
    trade_date: str = Field(description="成交日期 (YYYY-MM-DD)")
    instrument_id: int = Field(description="标的 ID")
    direction: Literal["buy", "sell"] = Field(description="方向 (buy/sell)")
    quantity: int = Field(description="成交数量")
    fill_price: float = Field(description="成交价格")
    fee: float = Field(default=0.0, description="手续费")
    slippage: float = Field(default=0.0, description="实际滑点")
    notes: str = Field(default="", description="人工备注")

    model_config = ConfigDict(strict=True, extra="ignore")


class UpdateIntentStatusRequest(BaseModel):
    """更新意图状态请求."""

    status: Literal["pending", "filled", "partially_filled", "cancelled", "expired"] = (
        Field(description="新状态")
    )

    model_config = ConfigDict(strict=True, extra="ignore")


class TradeIntentResponse(BaseModel):
    """交易意图响应."""

    intent_id: str
    strategy_id: str
    signal_date: str
    instrument_id: int
    direction: str
    target_weight: float
    current_weight: float
    delta_weight: float
    quantity: int | None = None
    status: str = "pending"

    model_config = ConfigDict(strict=True, extra="ignore")


class FillResponse(BaseModel):
    """成交记录响应."""

    fill_id: str
    intent_id: str
    strategy_id: str
    trade_date: str
    instrument_id: int
    direction: str
    quantity: int
    fill_price: float
    fee: float = 0.0
    slippage: float = 0.0
    notes: str = ""
    settlement_date: str = ""

    model_config = ConfigDict(strict=True, extra="ignore")


class PositionSnapshotResponse(BaseModel):
    """实际持仓快照响应."""

    snapshot_id: str
    strategy_id: str
    snapshot_date: str
    instrument_id: int
    quantity: int
    available_quantity: int
    average_cost: float
    market_value: float
    unrealized_pnl: float
    realized_pnl: float
    total_fees: float

    model_config = ConfigDict(strict=True, extra="ignore")


class PnlSummaryResponse(BaseModel):
    """P&L 汇总响应."""

    total_realized_pnl: float
    total_unrealized_pnl: float
    total_fees: float
    net_pnl: float

    model_config = ConfigDict(strict=True, extra="ignore")


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


class ComparisonMetricsResponse(BaseModel):
    """回测 vs 实际对比指标响应."""

    backtest_return: float
    actual_return: float
    return_diff: float
    return_diff_bps: float
    backtest_sharpe: float
    actual_sharpe: float
    backtest_total_cost: float
    actual_total_cost: float
    cost_drag_bps: float
    nav_correlation: float
    max_nav_diff_bps: float
    avg_daily_tracking_error_bps: float

    model_config = ConfigDict(strict=True, extra="ignore")


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


__all__ = [
    "ComparisonMetricsResponse",
    "FillResponse",
    "PnlSummaryResponse",
    "PositionSnapshotResponse",
    "RecordFillRequest",
    "TradeIntentResponse",
    "UpdateIntentStatusRequest",
    "to_comparison_response",
    "to_fill_response",
    "to_intent_response",
    "to_pnl_response",
    "to_position_response",
]
