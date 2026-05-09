"""
执行计划器类型定义 — dataclasses / enums.

供 planner.py (facade) 和子模块共同使用，避免循环导入。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from ditto_kernel.identity import InstrumentId
from ditto_kernel.order import OrderSide
from ditto_portfolio.accounting import Order

__all__ = [
    "BlockSeverity",
    "BlockedOrder",
    "ExecutionPlan",
]


class BlockSeverity(StrEnum):
    """订单阻塞严重程度。"""

    BLOCK = "block"
    DEFER = "defer"


@dataclass(frozen=True)
class BlockedOrder:
    """
    被阻止的订单 — 因风险控制或规则限制无法执行。

    Attributes:
        instrument_id: 标的 ID
        direction: 原始订单方向
        intended_quantity: 原始计划数量
        reason: 阻止原因
        severity: 阻止严重程度

    """

    instrument_id: InstrumentId
    direction: OrderSide
    intended_quantity: int
    reason: str
    severity: BlockSeverity


@dataclass(frozen=True)
class ExecutionPlan:
    """
    执行计划 — planner 的输出。

    Attributes:
        plan_id: 计划 ID
        trade_date: 交易日期
        orders: 待执行订单列表
        estimated_turnover: 预估成交额
        estimated_cost: 预估交易成本
        blocked_orders: 被阻止的订单列表

    """

    plan_id: str
    trade_date: str
    orders: tuple[Order, ...]
    estimated_turnover: float
    estimated_cost: float
    blocked_orders: tuple[BlockedOrder, ...]
