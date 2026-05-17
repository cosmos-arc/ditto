"""
PaperTradingRuntime — 纸上交易运行时编排器.

纯编排层：委托 PaperBrokerGateway 执行订单，委托 Account 应用成交。
不包含任何撮合/成交逻辑。
"""

from __future__ import annotations

from ditto_execution.broker.gateways.paper import PaperBrokerGateway
from ditto_execution.orders.model import Order
from ditto_execution.orders.ticket import OrderTicket
from ditto_portfolio.accounting.account import Account

__all__ = ["PaperTradingRuntime"]


class PaperTradingRuntime:
    """
    纸上交易运行时 — 最小冒烟测试级别的订单执行编排器.

    职责仅限于：
    1. 提交订单到 PaperBrokerGateway
    2. 获取 gateway 产出的成交
    3. 将成交应用到 Account

    不实现任何撮合、定价或风控逻辑。
    """

    def __init__(self, gateway: PaperBrokerGateway, account: Account) -> None:
        self._gateway = gateway
        self._account = account

    def execute_order(self, order: Order) -> OrderTicket:
        """
        执行订单：提交到 gateway -> 获取成交 -> 应用到账户.

        Args:
            order: 待执行订单

        Returns:
            填充完成的 OrderTicket

        """
        ticket = self._gateway.submit_order(order)
        fills = self._gateway.query_fills(order.order_id)
        for fill in fills:
            settle_date = fill.event_time.strftime("%Y-%m-%d")
            self._account.apply_fill(fill, settle_date=settle_date)
        return ticket
