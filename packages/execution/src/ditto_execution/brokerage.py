"""Execution brokerage ports."""

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
    Pending-order processing input for a brokerage adapter.

    Paper adapters may fill this from the current market slice; live adapters
    may ignore the bar map and query their gateway state instead.
    """

    step_time: datetime
    trade_date: str
    bars: dict[InstrumentId, MarketSnapshot]


class Brokerage(Protocol):
    """Brokerage port shared by simulation and live execution adapters."""

    def connect(self) -> None:
        """Establish the brokerage connection."""
        ...

    def get_account(self) -> AccountView:
        """Return the current read-only account view."""
        ...

    def place_order(self, order: Order) -> OrderTicket:
        """Submit an order."""
        ...

    def cancel_order(self, order_id: str) -> bool:
        """Cancel an order and report whether cancellation succeeded."""
        ...

    def process_pending(self, process_input: ProcessInput) -> tuple[FillEvent, ...]:
        """Process pending orders and return generated fills."""
        ...
