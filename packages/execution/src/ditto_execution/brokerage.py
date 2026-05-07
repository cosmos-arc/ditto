"""
Runtime-facing execution brokerage ports.

Brokerage is the higher-level runtime-facing port used by backtest/live execution
loops. It may wrap a BrokerGateway, but the adapter from Brokerage.place_order to
BrokerGateway.submit_order belongs in execution/application wiring, not in
backtest.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from ditto_kernel.identity import InstrumentId
from ditto_kernel.trading import MarketSnapshot
from ditto_portfolio.accounting.account import AccountView
from ditto_portfolio.accounting.fills import FillEvent
from ditto_portfolio.accounting.order_book import Order, OrderTicket

__all__ = ["Brokerage", "ProcessInput"]


@dataclass(frozen=True)
class ProcessInput:
    """
    Pending-order processing input for a runtime-facing brokerage.

    Paper adapters may fill this from the current market slice; live adapters
    may ignore the bar map and query their gateway state instead.
    """

    step_time: datetime
    trade_date: str
    bars: dict[InstrumentId, MarketSnapshot]


class Brokerage(Protocol):
    """
    Runtime-facing brokerage port for backtest/live execution loops.

    Implementations own order lifecycle progression through process_pending.
    A live runtime can adapt place_order to a BrokerGateway.submit_order call in
    execution/application wiring, while backtest implementations process fills
    directly from ProcessInput.
    """

    def connect(self) -> None:
        """Establish the brokerage connection."""
        ...

    def get_account(self) -> AccountView:
        """Return the current read-only account view."""
        ...

    def place_order(self, order: Order) -> OrderTicket:
        """place_order accepts an execution-loop order into the runtime."""
        ...

    def cancel_order(self, order_id: str) -> bool:
        """Cancel an order and report whether cancellation succeeded."""
        ...

    def process_pending(self, process_input: ProcessInput) -> tuple[FillEvent, ...]:
        """process_pending advances pending orders and returns generated fills."""
        ...
