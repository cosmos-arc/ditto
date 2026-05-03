"""Broker gateway contracts — Protocol for real and simulated broker adapters."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ditto_portfolio.accounting.account import AccountView
from ditto_portfolio.accounting.fills import FillEvent
from ditto_portfolio.accounting.order_book import Order, OrderTicket

__all__ = ["BrokerGateway"]


@runtime_checkable
class BrokerGateway(Protocol):
    """券商网关接口 — 对接真实或模拟券商系统."""

    def connect(self) -> None:
        """建立与券商系统的连接."""
        ...

    def get_account(self) -> AccountView:
        """获取当前账户状态快照."""
        ...

    def submit_order(self, order: Order) -> OrderTicket:
        """提交订单至券商系统."""
        ...

    def cancel_order(self, order_id: str) -> bool:
        """取消已提交的订单，返回是否成功."""
        ...

    def query_fills(self, order_id: str) -> tuple[FillEvent, ...]:
        """查询指定订单的成交记录."""
        ...
