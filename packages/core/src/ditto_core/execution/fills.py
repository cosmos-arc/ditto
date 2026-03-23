"""
FillOutcome -- 显式联合类型 (F4).

替代 v2 的 FillEvent | None + side-channel 模式。
FillModel 恢复纯函数语义，无隐式状态。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from ditto_core.accounting.order_book import OrderDirection

__all__ = [
    "FillEvent",
    "FillOutcome",
    "Filled",
    "NoFill",
]


class FillOutcome:
    """FillModel 的显式返回值基类。"""


@dataclass(frozen=True)
class Filled(FillOutcome):
    """成交。"""

    fill_event: FillEvent


@dataclass(frozen=True)
class NoFill(FillOutcome):
    """
    不成交 -- 明确原因，无隐式状态。

    Attributes:
        reason:
            不成交原因 (suspended / limit_up_deferred /
            limit_down_deferred / insufficient_auction /
            price_out_of_range)
        can_retry: True = 下一 step 可能成交，False = 该订单逻辑上无效

    """

    reason: str
    can_retry: bool


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

    """

    fill_id: str
    order_id: str
    instrument_id: str
    direction: OrderDirection
    filled_quantity: int
    fill_price: float
    fee: float
    slippage: float
    event_time: datetime
    cumulative_quantity: int
    leaves_quantity: int
