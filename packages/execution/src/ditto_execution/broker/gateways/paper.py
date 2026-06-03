"""PaperBrokerGateway — simulated broker for paper trading and testing."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Protocol
from uuid import uuid4

from ditto_kernel.identity import InstrumentId
from ditto_kernel.order import OrderSide, OrderType
from ditto_portfolio.accounting import FillEvent
from ditto_portfolio.accounting.account import Account, AccountView
from ditto_portfolio.accounting.cash import CashBook

from ditto_execution.errors import InsufficientFundsError
from ditto_execution.orders.book import OrderBook
from ditto_execution.orders.event import OrderEvent
from ditto_execution.orders.ids import ClientOrderId
from ditto_execution.orders.journal import InMemoryOrderEventJournal
from ditto_execution.orders.model import Order
from ditto_execution.orders.status import OrderStatus
from ditto_execution.orders.ticket import OrderTicket
from ditto_execution.orders.trigger import OrderTrigger

__all__ = ["OrderPreSubmitCheck", "PaperBrokerGateway"]

logger = logging.getLogger(__name__)


class OrderPreSubmitCheck(Protocol):
    """
    Pre-submit risk validation hook.

    Execution-internal Protocol matching RiskGate.pre_submit signature.
    Keeps ditto_execution free from ditto_risk imports while allowing
    structural subtyping with any RiskGate implementation.
    """

    def pre_submit(self, order: Order) -> Order | None:
        """Validate order pre-submit. Return modified order or None to reject."""
        ...


class PaperBrokerGateway:
    """Simulated broker gateway — fills orders immediately at resolved price."""

    def __init__(
        self,
        initial_cash: float = 0.0,
        last_prices: Mapping[InstrumentId, float] | None = None,
        risk_check: OrderPreSubmitCheck | None = None,
    ) -> None:
        """
        初始化 PaperBrokerGateway。

        Args:
            initial_cash: 初始可用资金（默认 0.0）。
            last_prices: 最新价格映射，用于市价单成交价解析。
                键为 ``InstrumentId``，值为最新价格。
            risk_check: 可选的预提交风控检查钩子，实现
                :class:`OrderPreSubmitCheck` Protocol。传入 ``None`` 跳过风控。

        """
        self._book = OrderBook(journal=InMemoryOrderEventJournal())
        self._fills: dict[str, list[FillEvent]] = {}
        self._account = Account(
            cash=CashBook(available=initial_cash, settled=initial_cash, frozen=0.0),
        )
        self._last_prices: Mapping[InstrumentId, float] = (
            last_prices if last_prices is not None else {}
        )
        self._risk_check = risk_check

    # -- BrokerGateway Protocol ------------------------------------------------

    def connect(self) -> None:
        """No-op — paper gateway has no external connection."""

    def get_account(self) -> AccountView:
        """Return a snapshot of the paper account state."""
        return self._account.get_view()

    def submit_order(self, order: Order) -> OrderTicket:
        """Submit order, fill immediately at resolved price, return ticket."""
        # Pre-submit risk check
        if self._risk_check is not None:
            checked = self._risk_check.pre_submit(order)
            if checked is None:
                return self._reject_on_submit(order)
            order = checked

        fill_price = self._resolve_fill_price(order)

        # BUY order cash check
        if order.direction == OrderSide.BUY:
            self._validate_buying_power(order, fill_price)

        ticket = self._book.submit(order)

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

        gw_fill = self._build_gw_fill(
            order,
            fill_price,
            fill_quantity=order.quantity,
            cumulative_quantity=order.quantity,
            leaves_quantity=0,
        )
        self._account.apply_fill(
            gw_fill,
            settle_date=gw_fill.event_time.strftime("%Y-%m-%d"),
        )

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

    def reject_order(self, order_id: str, reason: str) -> bool:
        """Reject an open order with a reason. Returns False if not possible."""
        cid = ClientOrderId(value=order_id)
        ticket = self._book.get(cid)
        if ticket is None:
            return False
        if ticket.status.is_terminal:
            return False
        event = OrderEvent(
            client_id=cid,
            trigger=OrderTrigger.REJECT,
            status=OrderStatus.REJECTED,
            message=reason,
        )
        rejected = ticket.with_reject(event)
        self._book.update(rejected, event=event)
        return True

    def query_fills(self, order_id: str) -> tuple[FillEvent, ...]:
        """Return gateway-reported fills for an order."""
        return tuple(self._fills.get(order_id, ()))

    # -- Simulation helpers (not in Protocol) ----------------------------------

    def simulate_fill(
        self,
        order_id: str,
        quantity: int,
        price: float,
    ) -> OrderTicket:
        """Simulate a partial or full fill — for testing / advanced simulation."""
        cid = ClientOrderId(value=order_id)
        ticket = self._book.get(cid)
        if ticket is None:
            raise KeyError(f"Order not found: {order_id}")

        actual_fill_qty = min(quantity, ticket.leaves_quantity)
        is_full = actual_fill_qty >= ticket.leaves_quantity
        status = OrderStatus.FILLED if is_full else OrderStatus.PARTIALLY_FILLED

        event = OrderEvent(
            client_id=ticket.order.client_id,
            trigger=OrderTrigger.FILL,
            status=status,
            fill_price=price,
            fill_quantity=actual_fill_qty,
        )
        filled_ticket = ticket.with_fill(
            quantity=actual_fill_qty,
            price=price,
            event=event,
        )
        self._book.update(filled_ticket, event=event)

        gw_fill = self._build_gw_fill(
            ticket.order,
            price,
            fill_quantity=actual_fill_qty,
            cumulative_quantity=filled_ticket.filled_quantity,
            leaves_quantity=filled_ticket.leaves_quantity,
        )
        self._account.apply_fill(
            gw_fill,
            settle_date=gw_fill.event_time.strftime("%Y-%m-%d"),
        )

        return filled_ticket

    # -- Private helpers -------------------------------------------------------

    def _validate_buying_power(self, order: Order, fill_price: float) -> None:
        """检查买单是否有足够的可用资金，不足则抛出 InsufficientFundsError。"""
        available_cash = self._account.get_view().cash.available
        cost = order.quantity * fill_price
        if cost > available_cash:
            msg = (
                f"资金不足: 订单 {order.order_id} 需要"
                f" {cost:.2f} 元, 可用余额 {available_cash:.2f} 元"
            )
            raise InsufficientFundsError(
                msg,
                order_id=order.order_id,
                required=cost,
                available=available_cash,
            )

    def _reject_on_submit(self, order: Order) -> OrderTicket:
        """Submit then immediately reject — risk gate blocked."""
        ticket = self._book.submit(order)
        event = OrderEvent(
            client_id=order.client_id,
            trigger=OrderTrigger.REJECT,
            status=OrderStatus.REJECTED,
            message="risk gate blocked",
        )
        rejected = ticket.with_reject(event)
        self._book.update(rejected, event=event)
        return rejected

    def _resolve_fill_price(self, order: Order) -> float:
        """Resolve fill price based on order type and available prices."""
        if order.price is not None:
            return order.price

        if order.order_type == OrderType.MARKET:
            last = self._last_prices.get(order.instrument_id)
            if last is not None:
                return last
            logger.warning(
                "Market order %s: no last price for instrument %s, using 0.0",
                order.client_id.value,
                order.instrument_id,
            )
            return 0.0

        return 0.0

    def _build_gw_fill(
        self,
        order: Order,
        fill_price: float,
        fill_quantity: int,
        cumulative_quantity: int,
        leaves_quantity: int,
    ) -> FillEvent:
        gw_fill = FillEvent(
            fill_id=f"paper-{uuid4().hex[:12]}",
            order_id=order.order_id,
            instrument_id=order.instrument_id,
            direction=order.direction,
            filled_quantity=fill_quantity,
            fill_price=fill_price,
            fee=0.0,
            slippage=0.0,
            event_time=datetime.now(tz=UTC),
            cumulative_quantity=cumulative_quantity,
            leaves_quantity=leaves_quantity,
        )
        self._fills.setdefault(order.order_id, []).append(gw_fill)
        return gw_fill
