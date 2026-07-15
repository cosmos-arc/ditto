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


class PositionBaselineRequest(BaseModel):
    """账户基线中的单只标的持仓。"""

    instrument_id: int = Field(description="标的 ID")
    quantity: int = Field(ge=0, description="持仓数量")
    available_quantity: int = Field(ge=0, description="可用数量")
    average_cost: float = Field(ge=0, description="平均成本")
    market_value: float = Field(ge=0, description="持仓市值")
    unrealized_pnl: float = Field(default=0, description="浮动盈亏")
    realized_pnl: float = Field(default=0, description="已实现盈亏")
    total_fees: float = Field(default=0, ge=0, description="累计费用")

    model_config = ConfigDict(strict=True, extra="forbid")


class ImportAccountBaselineRequest(BaseModel):
    """导入账户与持仓期初基线。"""

    account_id: str = Field(min_length=1, description="账户 ID")
    strategy_id: str = Field(min_length=1, description="策略 ID")
    snapshot_date: str = Field(description="快照日期 (YYYY-MM-DD)")
    cash_available: float = Field(ge=0, description="可用现金")
    cash_settled: float = Field(ge=0, description="已交收现金")
    cash_frozen: float = Field(ge=0, description="冻结现金")
    total_value: float = Field(ge=0, description="账户总资产")
    nav: float = Field(ge=0, description="单位净值")
    positions: list[PositionBaselineRequest] = Field(default_factory=list)
    replace_confirmed: bool = Field(default=False, description="确认覆盖已有基线")

    model_config = ConfigDict(strict=True, extra="forbid")


class AccountBaselineImportResponse(BaseModel):
    """账户基线导入结果。"""

    snapshot_id: str
    sleeve_id: str
    status: Literal["created", "unchanged", "replaced"]


class AccountBaselineResponse(BaseModel):
    """与信号日匹配的账户基线。"""

    snapshot_id: str
    sleeve_id: str
    account_id: str
    strategy_id: str
    snapshot_date: str
    cash_available: float
    cash_settled: float
    cash_frozen: float
    total_value: float
    nav: float
    exposure: float
    positions: list[PositionSnapshotResponse]


class TradeIntentResponse(BaseModel):
    """交易意图响应."""

    intent_id: str = Field(description="交易意图唯一标识")
    strategy_id: str = Field(description="策略 ID")
    signal_date: str = Field(description="信号日期 (YYYY-MM-DD)")
    instrument_id: int = Field(description="标的 ID")
    direction: str = Field(description="交易方向 (buy/sell)")
    target_weight: float = Field(description="目标权重")
    current_weight: float = Field(description="当前权重")
    delta_weight: float = Field(description="权重调整量")
    quantity: int | None = Field(default=None, description="建议交易数量")
    status: str = Field(default="pending", description="意图状态")

    model_config = ConfigDict(strict=True, extra="ignore")


class FillResponse(BaseModel):
    """成交记录响应."""

    fill_id: str = Field(description="成交唯一标识")
    intent_id: str = Field(description="关联交易意图 ID")
    strategy_id: str = Field(description="策略 ID")
    trade_date: str = Field(description="成交日期 (YYYY-MM-DD)")
    instrument_id: int = Field(description="标的 ID")
    direction: str = Field(description="交易方向 (buy/sell)")
    quantity: int = Field(description="成交数量")
    fill_price: float = Field(description="成交价格")
    fee: float = Field(default=0.0, description="手续费")
    slippage: float = Field(default=0.0, description="实际滑点")
    notes: str = Field(default="", description="人工备注")
    settlement_date: str = Field(default="", description="交收日期")

    model_config = ConfigDict(strict=True, extra="ignore")


class PositionSnapshotResponse(BaseModel):
    """实际持仓快照响应."""

    snapshot_id: str = Field(description="快照唯一标识")
    strategy_id: str = Field(description="策略 ID")
    snapshot_date: str = Field(description="快照日期 (YYYY-MM-DD)")
    instrument_id: int = Field(description="标的 ID")
    quantity: int = Field(description="持仓数量")
    available_quantity: int = Field(description="可用数量")
    average_cost: float = Field(description="平均成本价")
    market_value: float = Field(description="市值")
    unrealized_pnl: float = Field(description="浮动盈亏")
    realized_pnl: float = Field(description="已实现盈亏")
    total_fees: float = Field(description="累计手续费")

    model_config = ConfigDict(strict=True, extra="ignore")


class PnlSummaryResponse(BaseModel):
    """P&L 汇总响应."""

    total_realized_pnl: float = Field(description="已实现盈亏合计")
    total_unrealized_pnl: float = Field(description="浮动盈亏合计")
    total_fees: float = Field(description="累计手续费")
    net_pnl: float = Field(description="净盈亏 (已实现 + 浮动 - 手续费)")

    model_config = ConfigDict(strict=True, extra="ignore")


class ComparisonMetricsResponse(BaseModel):
    """回测 vs 实际对比指标响应."""

    backtest_return: float = Field(description="回测累计收益率 (%)")
    actual_return: float | None = Field(default=None, description="实际累计收益率 (%)")
    return_diff: float | None = Field(default=None, description="收益率差(百分点)")
    return_diff_bps: float | None = Field(default=None, description="收益率差值 (bps)")
    backtest_sharpe: float = Field(description="回测夏普比率")
    actual_sharpe: float = Field(description="实际夏普比率")
    backtest_total_cost: float = Field(description="回测累计交易成本")
    actual_total_cost: float = Field(description="实际累计交易成本")
    cost_drag_bps: float = Field(description="成本拖累(实际-回测)成本/初始资金 (bps)")
    nav_correlation: float = Field(description="回测与实际净值序列相关系数")
    max_nav_diff_bps: float = Field(description="回测与实际净值序列最大偏差 (bps)")
    avg_daily_tracking_error_bps: float = Field(description="日均跟踪误差 (bps)")

    model_config = ConfigDict(strict=True, extra="ignore")


class SignalDeviationItem(BaseModel):
    """信号-成交偏差项."""

    instrument_id: int = Field(description="标的 ID")
    signal_action: str = Field(description="信号动作 (buy/sell/hold)")
    signal_weight: float = Field(description="信号目标权重")
    actual_weight: float | None = Field(default=None, description="实际成交权重")
    deviation_bps: float | None = Field(default=None, description="信号-成交偏差 (bps)")
    fill_status: str = Field(default="unfilled", description="成交状态")

    model_config = ConfigDict(strict=True, extra="ignore")


class DeviationResponse(BaseModel):
    """信号-成交偏差报告."""

    strategy_id: str = Field(description="策略 ID")
    signal_date: str = Field(description="信号日期 (YYYY-MM-DD)")
    total_signals: int = Field(description="信号总数")
    filled: int = Field(description="已成交数")
    unfilled: int = Field(description="未成交数")
    items: list[SignalDeviationItem] = Field(description="偏差明细列表")

    model_config = ConfigDict(strict=True, extra="ignore")


class DailyDecisionReadinessResponse(BaseModel):
    """每日决策就绪状态响应."""

    status: Literal["ready", "blocked", "review"] = Field(description="就绪状态")
    reasons: list[str] = Field(description="就绪/阻塞原因")

    model_config = ConfigDict(strict=True, extra="ignore")


class DailyDecisionReportResponse(BaseModel):
    """每日决策驾驶舱报告响应."""

    strategy_id: str = Field(description="策略 ID")
    trade_date: str | None = Field(default=None, description="交易/信号日期")
    readiness: DailyDecisionReadinessResponse = Field(description="就绪状态")
    signal_intents: list[TradeIntentResponse] = Field(description="信号意图列表")
    positions: list[PositionSnapshotResponse] = Field(description="实际持仓快照")
    deviation: DeviationResponse | None = Field(
        default=None,
        description="信号-成交偏差报告",
    )
    pnl: PnlSummaryResponse | None = Field(default=None, description="P&L 汇总")

    model_config = ConfigDict(strict=True, extra="ignore")


__all__ = [
    "AccountBaselineImportResponse",
    "AccountBaselineResponse",
    "ComparisonMetricsResponse",
    "DailyDecisionReadinessResponse",
    "DailyDecisionReportResponse",
    "DeviationResponse",
    "FillResponse",
    "ImportAccountBaselineRequest",
    "PnlSummaryResponse",
    "PositionBaselineRequest",
    "PositionSnapshotResponse",
    "RecordFillRequest",
    "SignalDeviationItem",
    "TradeIntentResponse",
    "UpdateIntentStatusRequest",
]
