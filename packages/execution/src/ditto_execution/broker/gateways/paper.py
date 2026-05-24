"""PaperBrokerGateway — simulated broker for paper trading and testing."""

from __future__ import annotations

from datetime import UTC, datetime
from types import MappingProxyType
from uuid import uuid4

from ditto_portfolio.accounting import FillEvent
from ditto_portfolio.accounting.account import AccountView
from ditto_portfolio.accounting.cash import CashBook

from ditto_execution.orders.book import OrderBook
from ditto_execution.orders.event import OrderEvent
from ditto_execution.orders.ids import ClientOrderId
from ditto_execution.orders.journal import InMemoryOrderEventJournal
from ditto_execution.orders.model import Order
from ditto_execution.orders.status import OrderStatus
from ditto_execution.orders.ticket import OrderTicket
from ditto_execution.orders.trigger import OrderTrigger

__all__ = ["PaperBrokerGateway"]


class PaperBrokerGateway:
    """Simulated broker gateway — fills orders immediately at order price."""

    def __init__(self, initial_cash: float = 0.0) -> None:
        self._book = OrderBook(journal=InMemoryOrderEventJournal())
        self._fills: dict[str, list[FillEvent]] = {}
        self._initial_cash = initial_cash

    # -- BrokerGateway Protocol ------------------------------------------------

    def connect(self) -> None:
        """No-op — paper gateway has no external connection."""

    def get_account(self) -> AccountView:
        """Return a snapshot of the paper account state."""
        cash = CashBook(
            available=self._initial_cash,
            settled=self._initial_cash,
            frozen=0.0,
        )
        return AccountView(
            positions=MappingProxyType({}),
            cash=cash,
            total_value=cash.total,
            nav=cash.total,
            exposure=0.0,
        )

    def submit_order(self, order: Order) -> OrderTicket:
        """Submit order, fill immediately at order price, return ticket."""
        ticket = self._book.submit(order)
        # NOTE: 市价单 fill_price=0.0 是最小冒烟测试实现的简化；
        # 生产级实现应以 last close price 成交。
        fill_price = order.price if order.price is not None else 0.0

        # Apply fill
        fill_event = OrderEvent(
            client_id=order.client_id,
            trigger=OrderTrigger.FILL,
            status=OrderStatus.FILLED,
            fill_price=fill_price,
            fill_quantity=order.quantity,
        )
        filled_ticket = ticket.with_fill(
            quantity=order.quantity,
            price=fill_price,
            event=fill_event,
        )
        self._book.update(filled_ticket, event=fill_event)

        # Record gateway fill
        gw_fill = FillEvent(
            fill_id=f"paper-{uuid4().hex[:12]}",
            order_id=order.order_id,
            instrument_id=order.instrument_id,
            direction=order.direction,
            filled_quantity=order.quantity,
            fill_price=fill_price,
            fee=0.0,
            slippage=0.0,
            event_time=datetime.now(tz=UTC),
            cumulative_quantity=order.quantity,
            leaves_quantity=0,
        )
        self._fills.setdefault(order.order_id, []).append(gw_fill)

        return filled_ticket

    def cancel_order(self, order_id: str) -> bool:
        """Cancel an open order. Returns False for nonexistent or terminal orders."""
        cid = ClientOrderId(value=order_id)
        ticket = self._book.get(cid)
        if ticket is None:
            return False
        if ticket.status.is_terminal:
            return False
        self._book.cancel(cid)
        return True

    def query_fills(self, order_id: str) -> tuple[FillEvent, ...]:
        """Return gateway-reported fills for an order."""
        return tuple(self._fills.get(order_id, ()))
