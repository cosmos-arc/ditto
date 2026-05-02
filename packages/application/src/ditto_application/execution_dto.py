"""
人工执行闭环 — App 层共享 DTO + 跨层映射函数.

定义 TradeIntent / ManualExecutionFill / ActualPositionSnapshot 的 app 层 DTO，
以及与 Data 层 Record 之间的双向映射函数。

由 query / command / process 三层共同使用，
放在 app 包根目录以规避 R8 互斥规则限制。

映射规则：
  - InstrumentId (NewType[int]) ↔ int: 显式转换
  - 其余字段直接传递（str/float/int/bool）
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from ditto_execution.models import FillRecord, PositionRecord, SignalRecord

__all__ = [
    "ActualPositionSnapshot",
    "ManualExecutionFill",
    "TradeIntent",
    "fill_to_record",
    "intent_to_record",
    "record_to_fill",
    "record_to_intent",
    "record_to_snapshot",
    "snapshot_to_record",
]


# ===========================================================================
# App 层 DTO — 人工执行闭环核心对象
# ===========================================================================


@dataclass(frozen=True)
class TradeIntent:
    """
    交易意图 — 信号推导出的期望交易.

    从 Pipeline 输出的 TargetPortfolio 与当前持仓对比，
    delta_weight ≠ 0 时自动生成。

    Attributes:
        intent_id: 意图唯一标识 (UUID).
        strategy_id: 策略 ID.
        signal_date: 信号日期 (YYYY-MM-DD).
        instrument_id: 标的 ID.
        direction: 方向 (buy/sell).
        target_weight: 目标权重.
        current_weight: 当前权重.
        delta_weight: 权重偏差.
        quantity: 预估数量 (None = 待计算).
        status: 状态 (pending/filled/partially_filled/cancelled/expired).

    """

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


@dataclass(frozen=True)
class ManualExecutionFill:
    """
    人工成交记录.

    交易员录入的实际成交数据，包含成交价格、数量、费用等。

    Attributes:
        fill_id: 成交唯一标识 (UUID).
        intent_id: 关联交易意图 ID.
        strategy_id: 策略 ID.
        trade_date: 成交日期 (YYYY-MM-DD).
        instrument_id: 标的 ID.
        direction: 方向 (buy/sell).
        quantity: 成交数量.
        fill_price: 成交价格.
        fee: 手续费.
        slippage: 实际滑点.
        notes: 人工备注.

    """

    fill_id: str
    intent_id: str
    strategy_id: str
    trade_date: str
    instrument_id: int
    direction: str
    quantity: int
    fill_price: float
    fee: float
    slippage: float = 0.0
    notes: str = ""
    settlement_date: str = ""


@dataclass(frozen=True)
class ActualPositionSnapshot:
    """
    实际持仓快照 — 从 Fill 聚合.

    ManualTracker 从所有成交记录聚合生成，包含 T+1 交收规则。

    Attributes:
        snapshot_id: 快照唯一标识 (UUID).
        strategy_id: 策略 ID.
        snapshot_date: 快照日期 (YYYY-MM-DD).
        instrument_id: 标的 ID.
        quantity: 总持仓数量.
        available_quantity: 可卖数量 (T+1 冻结后).
        average_cost: 平均成本.
        market_value: 市值.
        unrealized_pnl: 未实现盈亏.
        realized_pnl: 已实现盈亏 (累计).
        total_fees: 累计交易费用.

    """

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


# ===========================================================================
# DTO → Record 映射 (app → data)
# ===========================================================================


def intent_to_record(intent: TradeIntent) -> SignalRecord:
    """TradeIntent DTO → SignalRecord."""
    return SignalRecord(
        intent_id=intent.intent_id,
        strategy_id=intent.strategy_id,
        signal_date=intent.signal_date,
        instrument_id=int(intent.instrument_id),
        direction=intent.direction,
        target_weight=intent.target_weight,
        current_weight=intent.current_weight,
        delta_weight=intent.delta_weight,
        quantity=intent.quantity,
        status=intent.status,
        created_at=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    )


def fill_to_record(fill: ManualExecutionFill) -> FillRecord:
    """ManualExecutionFill DTO → FillRecord."""
    return FillRecord(
        fill_id=fill.fill_id,
        intent_id=fill.intent_id,
        strategy_id=fill.strategy_id,
        trade_date=fill.trade_date,
        instrument_id=int(fill.instrument_id),
        direction=fill.direction,
        quantity=fill.quantity,
        fill_price=fill.fill_price,
        fee=fill.fee,
        slippage=fill.slippage,
        notes=fill.notes,
        settlement_date=fill.settlement_date,
        created_at=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    )


def snapshot_to_record(
    snapshot: ActualPositionSnapshot,
) -> PositionRecord:
    """ActualPositionSnapshot DTO → PositionRecord."""
    return PositionRecord(
        snapshot_id=snapshot.snapshot_id,
        strategy_id=snapshot.strategy_id,
        snapshot_date=snapshot.snapshot_date,
        instrument_id=int(snapshot.instrument_id),
        quantity=snapshot.quantity,
        available_quantity=snapshot.available_quantity,
        average_cost=snapshot.average_cost,
        market_value=snapshot.market_value,
        unrealized_pnl=snapshot.unrealized_pnl,
        realized_pnl=snapshot.realized_pnl,
        total_fees=snapshot.total_fees,
        created_at=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    )


# ===========================================================================
# Record → DTO 映射 (data → app)
# ===========================================================================


def record_to_intent(record: SignalRecord) -> TradeIntent:
    """SignalRecord → TradeIntent DTO."""
    return TradeIntent(
        intent_id=record.intent_id,
        strategy_id=record.strategy_id,
        signal_date=record.signal_date,
        instrument_id=record.instrument_id,
        direction=record.direction,
        target_weight=record.target_weight,
        current_weight=record.current_weight,
        delta_weight=record.delta_weight,
        quantity=record.quantity,
        status=record.status,
    )


def record_to_fill(record: FillRecord) -> ManualExecutionFill:
    """FillRecord → ManualExecutionFill DTO."""
    return ManualExecutionFill(
        fill_id=record.fill_id,
        intent_id=record.intent_id,
        strategy_id=record.strategy_id,
        trade_date=record.trade_date,
        instrument_id=record.instrument_id,
        direction=record.direction,
        quantity=record.quantity,
        fill_price=record.fill_price,
        fee=record.fee,
        slippage=record.slippage,
        notes=record.notes,
        settlement_date=record.settlement_date,
    )


def record_to_snapshot(record: PositionRecord) -> ActualPositionSnapshot:
    """PositionRecord → ActualPositionSnapshot DTO."""
    return ActualPositionSnapshot(
        snapshot_id=record.snapshot_id,
        strategy_id=record.strategy_id,
        snapshot_date=record.snapshot_date,
        instrument_id=record.instrument_id,
        quantity=record.quantity,
        available_quantity=record.available_quantity,
        average_cost=record.average_cost,
        market_value=record.market_value,
        unrealized_pnl=record.unrealized_pnl,
        realized_pnl=record.realized_pnl,
        total_fees=record.total_fees,
    )
