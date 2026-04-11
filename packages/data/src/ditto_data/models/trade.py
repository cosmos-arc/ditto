"""
人工执行闭环 — Data 本地持久化记录.

Data 层存储交易意图、人工成交、实际持仓所需的本地数据传输对象。
字段仅含标准库类型，不反向依赖 app/engine 包。
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = [
    "ActualPositionSnapshotRecord",
    "ManualExecutionFillRecord",
    "TradeIntentRecord",
]


# ===========================================================================
# TradeIntentRecord — 交易意图
# ===========================================================================


@dataclass(frozen=True)
class TradeIntentRecord:
    """
    交易意图持久化记录.

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
# ManualExecutionFillRecord — 人工成交
# ===========================================================================


@dataclass(frozen=True)
class ManualExecutionFillRecord:
    """
    人工成交持久化记录.

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


# ===========================================================================
# ActualPositionSnapshotRecord — 实际持仓快照
# ===========================================================================


@dataclass(frozen=True)
class ActualPositionSnapshotRecord:
    """
    实际持仓快照持久化记录.

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
    created_at: str = ""
