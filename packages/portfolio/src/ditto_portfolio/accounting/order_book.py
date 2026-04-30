"""
OrderBook / OrderTicket / Order — 订单簿 (F5: frozen dataclass).

Order 相关类型的内联定义。
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime
from enum import StrEnum

from ditto_kernel.identity import InstrumentId
from ditto_kernel.order import OrderSide

from ditto_portfolio.errors import StateTransitionError

__all__ = [
    "Order",
    "OrderBook",
    "OrderBookReadOnly",
    "OrderEvent",
    "OrderSide",
    "OrderStatus",
    "OrderTicket",
    "OrderType",
    "StateTransitionError",
]


class OrderType(StrEnum):
    """订单类型。"""

    MARKET = "market"
    LIMIT = "limit"
    STOP_MARKET = "stop_market"
    MARKET_ON_CLOSE = "market_on_close"


class OrderStatus(StrEnum):
    """订单状态。"""

    NEW = "new"
    SUBMITTED = "submitted"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELED = "canceled"
    REJECTED = "rejected"
    INVALID = "invalid"

    @property
    def is_terminal(self) -> bool:
        """终态：FILLED / CANCELED / REJECTED / INVALID。"""
        return self in (
            OrderStatus.FILLED,
            OrderStatus.CANCELED,
            OrderStatus.REJECTED,
            OrderStatus.INVALID,
        )


@dataclass(frozen=True)
class Order:
    """
    订单 — frozen dataclass，创建后不可变。

    Attributes:
        order_id: 订单唯一 ID
        instrument_id: 标的 ID
        order_type: 订单类型
        direction: 买/卖
        quantity: 股数
        price: LIMIT 单价格（市价单为 None）
        stop_price: STOP 单触发价
        created_at: 创建时间
        strategy_run_id: 关联策略运行 ID

    """

    order_id: str
    instrument_id: InstrumentId
    order_type: OrderType
    direction: OrderSide
    quantity: int
    price: float | None = None
    stop_price: float | None = None
    created_at: datetime = field(default_factory=lambda: datetime(2026, 1, 1))
    strategy_run_id: str = ""

    def with_quantity(self, qty: int) -> Order:
        """创建新 Order 实例，用于 PreTrade resize。"""
        return replace(self, quantity=qty)


@dataclass(frozen=True)
class OrderEvent:
    """
    订单事件 — 记录状态变更详情。

    Attributes:
        order_id: 关联订单 ID
        status: 订单状态
        fill_price: 成交价格（未成交为 None）
        fill_quantity: 本次成交数量
        fee: 手续费
        message: 附加信息（拒绝原因等）
        timestamp: 事件时间

    """

    order_id: str
    status: OrderStatus
    fill_price: float | None = None
    fill_quantity: int = 0
    fee: float = 0.0
    message: str | None = None
    timestamp: datetime = field(default_factory=lambda: datetime(2026, 1, 1))


@dataclass(frozen=True)
class OrderTicket:
    """
    订单票据 — frozen，状态变更通过 with_xxx() 返回新实例。

    Attributes:
        order: 原始订单
        status: 当前订单状态
        filled_quantity: 累计成交数量
        filled_price: 最近一次成交价格
        average_fill_price: 成交量加权平均成交价（VWAP）
        order_events: 订单事件历史

    """

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

    def with_fill(
        self,
        quantity: int,
        price: float,
        event: OrderEvent,
    ) -> OrderTicket:
        """记录成交，返回新 OrderTicket。"""
        new_filled = self.filled_quantity + quantity
        new_status = (
            OrderStatus.FILLED
            if new_filled >= self.order.quantity
            else OrderStatus.PARTIALLY_FILLED
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
        """撤销订单，终态不可撤销。"""
        if self.status.is_terminal:
            raise StateTransitionError(
                f"Cannot cancel order in terminal state: {self.status}"
            )
        return replace(
            self,
            status=OrderStatus.CANCELED,
            order_events=(*self.order_events, event),
        )

    def with_reject(self, event: OrderEvent) -> OrderTicket:
        """拒绝订单。"""
        return replace(
            self,
            status=OrderStatus.REJECTED,
            order_events=(*self.order_events, event),
        )

    def with_invalid(self, event: OrderEvent) -> OrderTicket:
        """B2: can_retry=False → INVALID 终态。"""
        if self.status.is_terminal:
            raise StateTransitionError(
                f"Cannot invalidate order in terminal state: {self.status}"
            )
        return replace(
            self,
            status=OrderStatus.INVALID,
            order_events=(*self.order_events, event),
        )

    def _calc_avg(self, price: float, quantity: int) -> float:
        """计算成交量加权平均成交价（VWAP）。"""
        if self.average_fill_price is None:
            return price
        total_qty = self.filled_quantity + quantity
        if total_qty == 0:
            return price
        return (
            self.average_fill_price * self.filled_quantity + price * quantity
        ) / total_qty


class OrderBookReadOnly:
    """
    OrderBook 只读视图。

    Note:
        使用普通类而非 frozen dataclass，因为 OrderBook 需要可变内部状态
        管理订单生命周期（submit / update / cancel），只读视图通过
        传递 dict 副本实现不可变性，无需 frozen dataclass。

    """

    def __init__(self, tickets: dict[str, OrderTicket]) -> None:
        self._tickets = tickets

    def get(self, order_id: str) -> OrderTicket | None:
        """获取订单票据。"""
        return self._tickets.get(order_id)

    def get_pending(self) -> tuple[OrderTicket, ...]:
        """获取所有未终结订单。"""
        return tuple(t for t in self._tickets.values() if not t.status.is_terminal)


class OrderBook:
    """
    订单簿 — 持有所有 OrderTicket，只允许通过受控方法修改.

    使用普通 class 而非 frozen dataclass，原因如下:

    1. **Mutable state**: 内部维护 ``dict[str, OrderTicket]`` 可变状态，
       需要在运行时动态增删改（submit / update / cancel），frozen dataclass
       无法满足此需求。
    2. **Lifecycle ownership**: OrderBook 管理订单的完整生命周期——从 submit
       到终态（filled / canceled / rejected / invalid），通过受控方法保证
       状态转换合法性。这是典型的 mutable owner 模式，不适合不可变值对象。

    Note:
        OrderTicket 本身是 frozen dataclass，状态变更通过 ``with_xxx()``
        返回新实例实现不可变性。OrderBook 持有对最新 OrderTicket 实例的
        引用，通过 ``update()`` 替换旧实例。

    """

    def __init__(self) -> None:
        self._tickets: dict[str, OrderTicket] = {}

    def get(self, order_id: str) -> OrderTicket | None:
        """获取订单票据。"""
        return self._tickets.get(order_id)

    def get_pending(self) -> tuple[OrderTicket, ...]:
        """获取所有未终结订单。"""
        return tuple(t for t in self._tickets.values() if not t.status.is_terminal)

    def submit(self, ticket: OrderTicket) -> None:
        """提交新订单。"""
        self._tickets[ticket.order.order_id] = ticket

    def update(self, ticket: OrderTicket) -> None:
        """更新订单票据。"""
        self._tickets[ticket.order.order_id] = ticket

    def cancel(self, order_id: str) -> None:
        """撤销订单，终态不可撤销。"""
        ticket = self._tickets.get(order_id)
        if ticket is None:
            raise KeyError(f"Order not found: {order_id}")
        if ticket.status.is_terminal:
            raise StateTransitionError(
                f"Cannot cancel order in terminal state: {ticket.status}"
            )
        event = OrderEvent(
            order_id=order_id,
            status=OrderStatus.CANCELED,
            timestamp=datetime(2026, 1, 1),
        )
        self._tickets[order_id] = ticket.with_cancel(event)

    def readonly_view(self) -> OrderBookReadOnly:
        """返回只读视图。"""
        return OrderBookReadOnly(dict(self._tickets))
