"""OrderBook + OrderBookReadOnly — 订单簿。"""

from __future__ import annotations

from ditto_execution.orders.event import OrderEvent
from ditto_execution.orders.ids import ClientOrderId
from ditto_execution.orders.journal import OrderEventJournal
from ditto_execution.orders.model import Order
from ditto_execution.orders.status import OrderStatus
from ditto_execution.orders.ticket import OrderTicket
from ditto_execution.orders.trigger import OrderTrigger

__all__ = ["OrderBook", "OrderBookReadOnly"]


class OrderBookReadOnly:
    """OrderBook 只读视图 — dict 副本实现不可变性。"""

    def __init__(self, tickets: dict[str, OrderTicket]) -> None:
        self._tickets = dict(tickets)  # 浅拷贝保证不可变性

    def get(self, client_id: ClientOrderId) -> OrderTicket | None:
        """获取订单票据。"""
        return self._tickets.get(client_id.value)

    def get_pending(self) -> tuple[OrderTicket, ...]:
        """获取所有未终结订单。"""
        return tuple(t for t in self._tickets.values() if not t.status.is_terminal)


class OrderBook:
    """订单簿 — 持有所有 OrderTicket，通过 Journal 追踪事件。"""

    def __init__(self, journal: OrderEventJournal) -> None:
        self._tickets: dict[str, OrderTicket] = {}
        self._journal = journal

    def get(self, client_id: ClientOrderId) -> OrderTicket | None:
        """获取订单票据。"""
        return self._tickets.get(client_id.value)

    def get_pending(self) -> tuple[OrderTicket, ...]:
        """获取所有未终结订单。"""
        return tuple(t for t in self._tickets.values() if not t.status.is_terminal)

    def submit(self, order: Order) -> OrderTicket:
        """提交新订单，返回 SUBMITTED 状态的 ticket。"""
        ticket = OrderTicket(order=order, status=OrderStatus.SUBMITTED)
        self._tickets[order.client_id.value] = ticket
        self._journal.append(
            OrderEvent(
                client_id=order.client_id,
                trigger=OrderTrigger.SUBMIT,
                status=OrderStatus.SUBMITTED,
            )
        )
        return ticket

    def update(self, ticket: OrderTicket, event: OrderEvent | None = None) -> None:
        """更新订单票据，可选地追加事件到 journal。"""
        self._tickets[ticket.order.client_id.value] = ticket
        if event is not None:
            self._journal.append(event)

    def restore_ticket(self, ticket: OrderTicket) -> None:
        """从 checkpoint 恢复订单票据，不追加新的 journal 事件。"""
        self._tickets[ticket.order.client_id.value] = ticket

    def cancel(self, client_id: ClientOrderId) -> None:
        """撤销订单。终态订单静默忽略（no-op）。"""
        ticket = self._tickets.get(client_id.value)
        if ticket is None:
            raise KeyError(f"Order not found: {client_id.value}")
        if ticket.status.is_terminal:  # 终态防御
            return
        event = OrderEvent(
            client_id=client_id,
            trigger=OrderTrigger.CANCEL,
            status=OrderStatus.CANCELED,
        )
        canceled = ticket.with_cancel(event)
        self._tickets[client_id.value] = canceled
        self._journal.append(event)

    def readonly_view(self) -> OrderBookReadOnly:
        """返回只读视图快照。"""
        return OrderBookReadOnly(dict(self._tickets))
