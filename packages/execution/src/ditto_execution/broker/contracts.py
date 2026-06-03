"""
Broker gateway contracts.

BrokerGateway is the low-level broker-system gateway port for paper or future
external broker systems. It defines operations such as submit_order and
query_fills; simulation-time process_pending belongs to the runtime-facing
Brokerage port. The protocol defines the seam and does not implement real
broker adapters.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ditto_portfolio.accounting import AccountView, FillEvent

from ditto_execution.orders.model import Order
from ditto_execution.orders.ticket import OrderTicket

__all__ = ["BrokerGateway"]


@runtime_checkable
class BrokerGateway(Protocol):
    """
    Broker-system gateway port for paper or future broker systems.

    The gateway submits orders and queries broker fills. It does not own
    execution-loop pending-order processing and does not implement real broker
    adapters.
    """

    def connect(self) -> None:
        """建立与券商系统的连接."""
        ...

    def get_account(self) -> AccountView:
        """获取当前账户状态快照."""
        ...

    def submit_order(self, order: Order) -> OrderTicket:
        """submit_order sends an order through the broker-system gateway port."""
        ...

    def cancel_order(self, order_id: str) -> bool:
        """取消已提交的订单，返回是否成功."""
        ...

    def reject_order(self, order_id: str, reason: str) -> bool:
        """拒绝订单并记录原因，返回是否成功."""
        ...

    def query_fills(self, order_id: str) -> tuple[FillEvent, ...]:
        """query_fills returns broker-reported fills for an order."""
        ...
