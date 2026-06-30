"""
FillEvent — 单次成交事件。

从 execution/fills.py 提升到 accounting 层，消除 accounting ↔ execution 循环依赖。
FillEvent 描述"成交事实"，与 Account.apply_fill() 紧密耦合，属于 accounting 领域。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from ditto_kernel.identity import InstrumentId
from ditto_kernel.order import OrderSide

__all__ = ["FillEvent"]


@dataclass(frozen=True)
class FillEvent:
    """
    单次成交事件 -- Brokerage 产出（仅在确实成交时产生）。

    Attributes:
        fill_id: 成交 ID
        order_id: 关联订单 ID
        instrument_id: 标的 ID
        direction: 买/卖
        filled_quantity: 本次成交量
        fill_price: 成交价格
        fee: 交易费用
        slippage: 滑点
        event_time: 成交时间
        cumulative_quantity: 该订单累计已成交量
        leaves_quantity: 该订单剩余未成交量
        correlation_id: 关联 ID（可追溯 order → fill → account）

    """

    fill_id: str
    order_id: str
    instrument_id: InstrumentId
    direction: OrderSide
    filled_quantity: int
    fill_price: float
    fee: float
    slippage: float
    event_time: datetime
    cumulative_quantity: int
    leaves_quantity: int
    correlation_id: str | None = None
