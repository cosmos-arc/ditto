"""Position — 单个标的的持仓状态 (frozen dataclass)."""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["Position"]


@dataclass(frozen=True)
class Position:
    """
    单个标的的持仓状态。

    Attributes:
        instrument_id: 标的 ID（如 "159915.SZ"）
        quantity: 总持仓数量（股数）
        available_quantity: 可卖数量（扣除 T+1 冻结）
        average_cost: 加权平均成本
        market_value: 当前市值
        unrealized_pnl: 浮动盈亏
        realized_pnl: 已实现盈亏（累计）
        total_fees: 累计交易费用

    """

    instrument_id: str
    quantity: int
    available_quantity: int
    average_cost: float
    market_value: float
    unrealized_pnl: float
    realized_pnl: float
    total_fees: float
