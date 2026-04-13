"""交易闭环 API 模型."""

from __future__ import annotations

from typing import Literal

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


class ComparisonMetricsResponse(BaseModel):
    """回测 vs 实际对比指标响应."""

    backtest_return: float
    actual_return: float | None
    return_diff: float | None
    return_diff_bps: float | None
    backtest_sharpe: float
    actual_sharpe: float
    backtest_total_cost: float
    actual_total_cost: float
    cost_drag_bps: float
    nav_correlation: float
    max_nav_diff_bps: float
    avg_daily_tracking_error_bps: float

    model_config = ConfigDict(strict=True, extra="ignore")


__all__ = [
    "ComparisonMetricsResponse",
    "FillResponse",
    "PnlSummaryResponse",
    "PositionSnapshotResponse",
    "RecordFillRequest",
    "TradeIntentResponse",
    "UpdateIntentStatusRequest",
]
