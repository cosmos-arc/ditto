"""OrderEvent — 订单事件，记录状态变更详情。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from ditto_execution.orders.ids import ClientOrderId
from ditto_execution.orders.status import OrderStatus
from ditto_execution.orders.trigger import OrderTrigger

__all__ = ["OrderEvent"]


@dataclass(frozen=True)
class OrderEvent:
    """
    订单事件 — 记录状态变更详情。

    Attributes:
        client_id: 关联客户端订单 ID
        trigger: 触发本次状态变更的触发器
        status: 变更后的订单状态
        fill_price: 成交价格（未成交为 None）
        fill_quantity: 本次成交数量
        fee: 手续费
        message: 附加信息（拒绝原因等）
        timestamp: 事件时间

    """

    client_id: ClientOrderId
    trigger: OrderTrigger
    status: OrderStatus
    fill_price: float | None = None
    fill_quantity: int = 0
    fee: float = 0.0
    message: str | None = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(tz=UTC))
