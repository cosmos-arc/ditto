"""
人工执行闭环 — Data 本地持久化记录.

Data 层存储交易意图、人工成交、实际持仓所需的本地数据传输对象。
字段仅含标准库类型，不反向依赖 app/engine 包。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

__all__ = [
    "STANDARD_BROKER_EVENT_TYPES",
    "AccountSnapshotRecord",
    "BrokerEventRecord",
    "BrokerEventType",
    "FillAdjustmentRecord",
    "FillAdjustmentType",
    "FillRecord",
    "PositionRecord",
    "SignalRecord",
    "require_standard_broker_event_type",
]

type BrokerEventType = Literal[
    "connect",
    "order_ack",
    "fill",
    "fill_query_error",
    "cancel",
    "reject",
    "account_update",
]

type FillAdjustmentType = Literal["void", "replace"]

STANDARD_BROKER_EVENT_TYPES: tuple[BrokerEventType, ...] = (
    "connect",
    "order_ack",
    "fill",
    "fill_query_error",
    "cancel",
    "reject",
    "account_update",
)


def require_standard_broker_event_type(event_type: str) -> BrokerEventType:
    """Return a standard broker event type or fail closed for adapter drift."""
    if event_type not in STANDARD_BROKER_EVENT_TYPES:
        msg = f"Unsupported broker event type: {event_type}"
        raise ValueError(msg)
    return event_type


# ===========================================================================
# SignalRecord — 交易信号
# ===========================================================================


@dataclass(frozen=True)
class SignalRecord:
    """
    交易信号持久化记录.

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
        created_at: 创建时间 (RFC3339).

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
    created_at: str = ""


# ===========================================================================
# FillRecord — 成交记录
# ===========================================================================


@dataclass(frozen=True)
class FillRecord:
    """
    成交持久化记录.

    Attributes:
        fill_id: 成交唯一标识 (UUID).
        intent_id: 关联交易信号 ID.
        strategy_id: 策略 ID.
        trade_date: 成交日期 (YYYY-MM-DD).
        instrument_id: 标的 ID.
        direction: 方向 (buy/sell).
        quantity: 成交数量.
        fill_price: 成交价格.
        fee: 手续费.
        slippage: 实际滑点.
        notes: 人工备注.
        settlement_date: 交收日期 (T+1).
        created_at: 创建时间 (RFC3339).

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
    created_at: str = ""


@dataclass(frozen=True)
class FillAdjustmentRecord:
    """Append-only event that voids or replaces one immutable fill."""

    adjustment_id: str
    fill_id: str
    adjustment_type: FillAdjustmentType
    replacement_fill_id: str | None
    reason: str
    created_at: str


# ===========================================================================
# AccountSnapshotRecord — 账户快照
# ===========================================================================


@dataclass(frozen=True)
class AccountSnapshotRecord:
    """
    账户快照持久化记录.

    Attributes:
        snapshot_id: 快照唯一标识.
        run_id: 运行 ID，用于把账户状态归属到一次执行/回测运行.
        strategy_id: 策略 ID.
        account_id: 账户 ID.
        snapshot_date: 快照日期 (YYYY-MM-DD).
        cash_available: 可用现金.
        cash_settled: 已结算现金.
        cash_frozen: 冻结现金.
        total_value: 总资产.
        nav: 净值.
        exposure: 持仓总市值.
        created_at: 创建时间 (RFC3339).

    """

    snapshot_id: str
    run_id: str
    strategy_id: str
    account_id: str
    snapshot_date: str
    cash_available: float
    cash_settled: float
    cash_frozen: float
    total_value: float
    nav: float
    exposure: float
    created_at: str = ""


# ===========================================================================
# BrokerEventRecord — 标准化券商网关事件
# ===========================================================================


@dataclass(frozen=True)
class BrokerEventRecord:
    """
    标准化券商事件持久化记录.

    Attributes:
        event_id: 事件唯一标识.
        run_id: 运行 ID，用于把 live/paper 事件归属到一次执行运行.
        broker: 券商或模拟网关标识.
        event_type: 标准事件类型，如 order_ack/fill/fill_query_error/
            cancel/reject/account_update.
        event_time: 券商事件时间 (RFC3339).
        order_id: 本地订单 ID.
        broker_order_id: 券商侧订单 ID.
        fill_id: 成交 ID（成交事件时可用）.
        instrument_id: 标的 ID.
        status: 券商侧状态标准化值.
        correlation_id: 跨审计/订单/券商事件的关联键.
        payload: 保留的网关原始/扩展字段.
        created_at: 本地写入时间 (RFC3339).

    """

    event_id: str
    run_id: str
    broker: str
    event_type: str
    event_time: str
    order_id: str | None = None
    broker_order_id: str | None = None
    fill_id: str | None = None
    instrument_id: int | None = None
    status: str | None = None
    correlation_id: str | None = None
    payload: dict[str, object] = field(default_factory=dict)
    created_at: str = ""


# ===========================================================================
# PositionRecord — 持仓快照
# ===========================================================================


@dataclass(frozen=True)
class PositionRecord:
    """
    持仓快照持久化记录.

    Attributes:
        snapshot_id: 快照唯一标识 (UUID).
        run_id: 运行 ID，用于把持仓快照归属到一次执行/回测运行.
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
        created_at: 创建时间 (RFC3339).

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
    run_id: str = ""
    created_at: str = ""
