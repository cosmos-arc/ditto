"""交易闭环 API 模型."""

from __future__ import annotations

from datetime import date
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StringConstraints

type NonBlankStr = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1),
]


def _validate_iso_calendar_date(value: str) -> str:
    """Keep the transport value as a string while rejecting impossible dates."""
    try:
        date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("must be a valid YYYY-MM-DD calendar date") from exc
    return value


type IsoCalendarDateStr = Annotated[
    str,
    StringConstraints(pattern=r"^\d{4}-\d{2}-\d{2}$"),
    AfterValidator(_validate_iso_calendar_date),
]


class RecordFillRequest(BaseModel):
    """录入成交请求."""

    fill_id: NonBlankStr = Field(description="成交唯一标识")
    intent_id: NonBlankStr = Field(description="关联交易意图 ID")
    strategy_id: NonBlankStr = Field(description="策略 ID")
    trade_date: IsoCalendarDateStr = Field(description="成交日期 (YYYY-MM-DD)")
    instrument_id: int = Field(gt=0, description="标的 ID")
    direction: Literal["buy", "sell"] = Field(description="方向 (buy/sell)")
    quantity: int = Field(gt=0, description="成交数量")
    fill_price: float = Field(gt=0, description="成交价格")
    fee: float = Field(default=0.0, ge=0, description="手续费")
    slippage: float = Field(default=0.0, description="实际滑点")
    notes: str = Field(default="", description="人工备注")

    model_config = ConfigDict(strict=True, extra="forbid", allow_inf_nan=False)


class VoidFillRequest(BaseModel):
    """以 append-only 事件作废一笔原始成交。"""

    adjustment_id: NonBlankStr = Field(description="修正事件唯一标识")
    reason: NonBlankStr = Field(description="人工修正原因")

    model_config = ConfigDict(strict=True, extra="forbid")


class ReplaceFillRequest(BaseModel):
    """追加一笔替换成交并链接原始成交。"""

    adjustment_id: NonBlankStr = Field(description="修正事件唯一标识")
    replacement_fill_id: NonBlankStr = Field(description="替换成交唯一标识")
    trade_date: IsoCalendarDateStr = Field(description="替换成交日期 (YYYY-MM-DD)")
    quantity: int = Field(gt=0, description="替换成交数量")
    fill_price: float = Field(gt=0, description="替换成交价格")
    reason: NonBlankStr = Field(description="人工修正原因")
    fee: float = Field(default=0.0, ge=0, description="手续费")
    slippage: float = Field(default=0.0, description="实际滑点")
    notes: str = Field(default="", description="人工备注")

    model_config = ConfigDict(strict=True, extra="forbid", allow_inf_nan=False)


class UpdateIntentStatusRequest(BaseModel):
    """更新意图状态请求."""

    status: Literal[
        "pending",
        "filled",
        "partially_filled",
        "cancelled",
        "expired",
        "superseded",
    ] = Field(description="新状态")

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

    model_config = ConfigDict(
        strict=True,
        extra="forbid",
        allow_inf_nan=False,
    )


class ImportAccountBaselineRequest(BaseModel):
    """导入账户与持仓期初基线。"""

    account_id: str = Field(min_length=1, description="账户 ID")
    strategy_id: str = Field(min_length=1, description="策略 ID")
    snapshot_date: str = Field(
        pattern=r"^\d{4}-\d{2}-\d{2}$",
        description="快照日期 (YYYY-MM-DD)",
    )
    cash_available: float = Field(ge=0, description="可用现金")
    cash_settled: float = Field(ge=0, description="已交收现金")
    cash_frozen: float = Field(ge=0, description="冻结现金")
    total_value: float = Field(ge=0, description="账户总资产")
    nav: float = Field(ge=0, description="单位净值")
    positions: list[PositionBaselineRequest] = Field(default_factory=list)
    replace_confirmed: bool = Field(default=False, description="确认覆盖已有基线")

    model_config = ConfigDict(
        strict=True,
        extra="forbid",
        allow_inf_nan=False,
    )


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


class FillAdjustmentResponse(BaseModel):
    """不可变成交修正事件响应。"""

    adjustment_id: str
    fill_id: str
    adjustment_type: Literal["void", "replace"]
    replacement_fill_id: str | None = None
    reason: str
    created_at: str

    model_config = ConfigDict(strict=True, extra="forbid")


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


type DailyDecisionReasonCode = Literal[
    "NO_ACTIVE_STRATEGY",
    "REQUIRED_DATA_NOT_READY",
    "ACCOUNT_BASELINE_MISSING",
    "EOD_RUN_MISSING",
    "EOD_RUN_FAILED",
    "EOD_RUN_INCOMPLETE",
    "SIGNAL_PACKAGE_MISSING",
    "SIGNAL_INTENT_MISMATCH",
    "CHECKSUM_MISMATCH",
    "NO_REBALANCE_REQUIRED",
    "RISK_WARNING",
    "TRADE_DATE_MISMATCH",
    "RERUN_CONFLICT",
    "FILL_QUANTITY_EXCEEDED",
    "QUANTITY_UNAVAILABLE",
    "READY_FOR_REVIEW",
]


class DailyDecisionIdentityResponse(BaseModel):
    """策略、账户与 D→D+1 日期身份。"""

    strategy_id: str
    strategy_version: str | None = None
    account_id: str | None = None
    sleeve_id: str | None = None
    signal_date: str | None = None
    decision_date: str | None = None
    intended_trade_date: str | None = None

    model_config = ConfigDict(strict=True, extra="forbid")


class DailyDecisionV2ReadinessResponse(BaseModel):
    """后端判定的 readiness 与稳定 reason code。"""

    status: Literal["ready", "blocked", "review"]
    reason_codes: list[DailyDecisionReasonCode]
    details: list[str]

    model_config = ConfigDict(strict=True, extra="forbid")


class DailyDecisionDatasetStateResponse(BaseModel):
    """一个必需数据集的 EOD 就绪证据。"""

    dataset: str
    status: Literal["ready", "missing", "stale", "dq_failed", "unknown"]
    snapshot_id: str | None = None
    reason: str = ""

    model_config = ConfigDict(strict=True, extra="forbid")


class DailyDecisionDataResponse(BaseModel):
    """策略所需数据、snapshot 与 DQ 证据。"""

    required_datasets: list[str]
    snapshot_ids: dict[str, str]
    dataset_states: list[DailyDecisionDatasetStateResponse]
    freshness: Literal["ready", "blocked"]
    dq_state: Literal["passed", "failed"]

    model_config = ConfigDict(strict=True, extra="forbid")


class DailyDecisionRunPackageResponse(BaseModel):
    """确定性 EOD run 与持久化 Signal Package 证据。"""

    outcome: str
    batch_key: str | None = None
    artifact_id: str | None = None
    conflict_artifact_id: str | None = None
    checksum: str | None = None
    checksum_valid: bool
    no_rebalance: bool
    factor_evidence: dict[str, dict[str, float]]
    risk_evidence: list[str]

    model_config = ConfigDict(strict=True, extra="forbid")


class DailyDecisionAccountPositionsResponse(BaseModel):
    """信号日可用的完整账户基线。"""

    baseline_id: str | None = None
    account_id: str | None = None
    sleeve_id: str | None = None
    cash_available: float | None = None
    cash_settled: float | None = None
    cash_frozen: float | None = None
    total_value: float | None = None
    nav: float | None = None
    exposure: float | None = None
    as_of: str | None = None
    positions: list[PositionSnapshotResponse]

    model_config = ConfigDict(strict=True, extra="forbid")


class DailyDecisionActionResponse(BaseModel):
    """一个可人工复核的建议动作及执行进度。"""

    intent_id: str
    instrument_id: int
    direction: str
    target_weight: float
    current_weight: float
    delta_weight: float
    raw_quantity: int | None = None
    rounded_quantity: int | None = None
    suggested_quantity: int | None = None
    reference_price: float | None = None
    lot_size: int | None = None
    cash_impact: float | None = None
    reason: str | None = None
    sizing_readiness: Literal["ready", "review", "blocked"] | None = None
    risk_flags: list[str]
    intent_status: str | None = None
    filled_quantity: int
    remaining_quantity: int | None = None

    model_config = ConfigDict(strict=True, extra="forbid")


class DailyDecisionExecutionReviewResponse(BaseModel):
    """当前有效成交、偏差、PnL 与未解决冲突。"""

    effective_fills: list[FillResponse]
    deviation: DeviationResponse | None = None
    pnl: PnlSummaryResponse | None = None
    exceptions: list[str]
    unresolved_conflicts: list[str]

    model_config = ConfigDict(strict=True, extra="forbid")


class DailyDecisionV2Response(BaseModel):
    """Daily Decision V2 分区 read model。"""

    identity: DailyDecisionIdentityResponse
    readiness: DailyDecisionV2ReadinessResponse
    data: DailyDecisionDataResponse
    run_package: DailyDecisionRunPackageResponse
    account_positions: DailyDecisionAccountPositionsResponse
    actions: list[DailyDecisionActionResponse]
    execution_review: DailyDecisionExecutionReviewResponse

    model_config = ConfigDict(
        strict=True,
        extra="forbid",
        json_schema_extra={
            "example": {
                "identity": {"strategy_id": "seed_etf_industry_rotation"},
                "readiness": {"status": "ready", "reason_codes": []},
                "data": {"required_datasets": ["etf_daily"]},
                "run_package": {"outcome": "completed"},
                "account_positions": {"as_of": "2026-07-16"},
                "actions": [],
                "execution_review": {"unresolved_conflicts": []},
            }
        },
    )


class DailyDecisionV3PortfolioConstructionResponse(BaseModel):
    """Portfolio construction outcome and solver evidence."""

    status: str
    mode: str | None = None
    policy_digest: str | None = None
    solver: str | None = None
    solver_version: str | None = None
    solver_status: str | None = None
    duration_ms: float | None = None
    failure_code: str | None = None

    model_config = ConfigDict(strict=True, extra="forbid", allow_inf_nan=False)


class DailyDecisionV3TailRiskResponse(BaseModel):
    """Positive-loss Historical ES99 headline and VaR diagnostics."""

    historical_es99: float | None
    historical_var99: float | None
    parametric_var99: float | None
    monte_carlo_var99: float | None
    monte_carlo_seed: int | None

    model_config = ConfigDict(strict=True, extra="forbid", allow_inf_nan=False)


class DailyDecisionV3FactorRiskResponse(BaseModel):
    """Factor-risk availability and Euler contribution evidence."""

    availability: Literal["available", "partial", "unavailable"]
    total_risk: float | None
    marginal_contributions: dict[str, float]
    percentage_contributions: dict[str, float]
    euler_residual: float | None

    model_config = ConfigDict(strict=True, extra="forbid", allow_inf_nan=False)


class DailyDecisionV3StressResponse(BaseModel):
    """Versioned stress catalog result payload."""

    catalog_version: str
    losses: dict[str, float]
    unavailable_scenarios: list[str] = Field(default_factory=list)

    model_config = ConfigDict(strict=True, extra="forbid", allow_inf_nan=False)


class DailyDecisionV3ReconciliationResponse(BaseModel):
    """Three-layer reconciliation status without automatic repair controls."""

    status: str
    differences: list[str]
    alert_idempotency_key: str | None

    model_config = ConfigDict(strict=True, extra="forbid")


class DailyDecisionV3ProvenanceResponse(BaseModel):
    """Temporal cutoffs, source revisions, and report generation time."""

    decision_time: str | None
    knowledge_cutoff: str | None
    publication_cutoff: str | None
    source_snapshot_ids: list[str]
    generated_at: str | None

    model_config = ConfigDict(strict=True, extra="forbid")


class DailyDecisionV3Response(BaseModel):
    """V2 cockpit plus the complete typed R4 risk decision surface."""

    v2: DailyDecisionV2Response
    readiness: Literal["ready", "blocked", "review"]
    blocking_reasons: list[str]
    portfolio_construction: DailyDecisionV3PortfolioConstructionResponse
    tail_risk: DailyDecisionV3TailRiskResponse
    factor_risk: DailyDecisionV3FactorRiskResponse
    stress_tests: DailyDecisionV3StressResponse
    reconciliation: DailyDecisionV3ReconciliationResponse
    provenance: DailyDecisionV3ProvenanceResponse

    model_config = ConfigDict(strict=True, extra="forbid", allow_inf_nan=False)


__all__ = [
    "AccountBaselineImportResponse",
    "AccountBaselineResponse",
    "ComparisonMetricsResponse",
    "DailyDecisionAccountPositionsResponse",
    "DailyDecisionActionResponse",
    "DailyDecisionDataResponse",
    "DailyDecisionDatasetStateResponse",
    "DailyDecisionExecutionReviewResponse",
    "DailyDecisionIdentityResponse",
    "DailyDecisionReadinessResponse",
    "DailyDecisionReportResponse",
    "DailyDecisionRunPackageResponse",
    "DailyDecisionV2ReadinessResponse",
    "DailyDecisionV2Response",
    "DailyDecisionV3FactorRiskResponse",
    "DailyDecisionV3PortfolioConstructionResponse",
    "DailyDecisionV3ProvenanceResponse",
    "DailyDecisionV3ReconciliationResponse",
    "DailyDecisionV3Response",
    "DailyDecisionV3StressResponse",
    "DailyDecisionV3TailRiskResponse",
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
