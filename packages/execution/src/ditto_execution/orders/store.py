"""Order store — 订单持久化接口。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

__all__ = ["OrderRecord", "OrderStore"]


@dataclass(frozen=True)
class OrderRecord:
    """Execution-owned order record for order persistence contracts."""

    order_id: str
    strategy_id: str
    trade_date: str
    instrument_id: int
    side: str
    quantity: int
    status: str = "pending"


class OrderStore(Protocol):
    """Persistence contract for execution orders."""

    def save_order(self, record: OrderRecord) -> None:
        """Persist one execution order."""
        ...

    def get_order(self, order_id: str) -> OrderRecord | None:
        """Return one execution order by id."""
        ...

    def list_orders(
        self,
        strategy_id: str,
        trade_date: str | None = None,
    ) -> list[OrderRecord]:
        """List execution orders for a strategy."""
        ...
