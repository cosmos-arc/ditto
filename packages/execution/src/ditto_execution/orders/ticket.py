"""OrderTicket — 订单票据，集成 FSM 状态转换。"""

from __future__ import annotations

from dataclasses import dataclass, replace

from ditto_execution.orders.event import OrderEvent
from ditto_execution.orders.fsm import transition
from ditto_execution.orders.model import Order
from ditto_execution.orders.status import OrderStatus
from ditto_execution.orders.trigger import OrderTrigger

__all__ = ["OrderTicket"]


@dataclass(frozen=True)
class OrderTicket:
    """订单票据 — frozen，状态变更通过 with_xxx() 返回新实例。"""

    order: Order
    status: OrderStatus = OrderStatus.NEW
    filled_quantity: int = 0
    filled_price: float | None = None
    average_fill_price: float | None = None
    order_events: tuple[OrderEvent, ...] = ()

    @property
    def leaves_quantity(self) -> int:
        """剩余未成交数量。"""
        return self.order.quantity - self.filled_quantity

    def with_fill(self, quantity: int, price: float, event: OrderEvent) -> OrderTicket:
        """记录成交，返回新 OrderTicket。"""
        if quantity <= 0:
            raise ValueError(f"fill quantity must be positive, got {quantity}")
        new_filled = self.filled_quantity + quantity
        new_status = transition(
            self.status,
            OrderTrigger.FILL,
            fill_qty=quantity,
            leaves_qty=self.leaves_quantity,
        )
        return replace(
            self,
            filled_quantity=new_filled,
            filled_price=price,
            average_fill_price=self._calc_avg(price, quantity),
            status=new_status,
            order_events=(*self.order_events, event),
        )

    def with_cancel(self, event: OrderEvent) -> OrderTicket:
        """撤销订单。"""
        return self._apply_trigger(OrderTrigger.CANCEL, event)

    def with_reject(self, event: OrderEvent) -> OrderTicket:
        """拒绝订单。"""
        return self._apply_trigger(OrderTrigger.REJECT, event)

    def with_invalid(self, event: OrderEvent) -> OrderTicket:
        """标记无效。"""
        return self._apply_trigger(OrderTrigger.INVALIDATE, event)

    def _apply_trigger(self, trigger: OrderTrigger, event: OrderEvent) -> OrderTicket:
        new_status = transition(self.status, trigger)
        return replace(
            self,
            status=new_status,
            order_events=(*self.order_events, event),
        )

    def _calc_avg(self, price: float, quantity: int) -> float:
        """计算 VWAP（成交量加权平均成交价）。"""
        if self.average_fill_price is None:
            return price
        total_qty = self.filled_quantity + quantity
        if total_qty == 0:
            return price
        return (
            self.average_fill_price * self.filled_quantity + price * quantity
        ) / total_qty
