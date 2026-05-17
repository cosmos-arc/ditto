"""Order 模型 — 使用 kernel OrderType + OrderSide。"""

from __future__ import annotations

from dataclasses import dataclass, replace

from ditto_kernel.identity import InstrumentId
from ditto_kernel.order import OrderSide, OrderType

from ditto_execution.orders.ids import ClientOrderId

__all__ = ["Order"]


@dataclass(frozen=True)
class Order:
    """订单 — frozen dataclass，创建后不可变。"""

    client_id: ClientOrderId
    instrument_id: InstrumentId
    order_type: OrderType
    direction: OrderSide
    quantity: int
    price: float | None = None
    stop_price: float | None = None

    @property
    def order_id(self) -> str:
        """兼容属性 — 返回 client_id 的字符串值。"""
        return self.client_id.value

    def with_quantity(self, qty: int) -> Order:
        """返回指定数量的新 Order（不可变更新）。"""
        return replace(self, quantity=qty)
