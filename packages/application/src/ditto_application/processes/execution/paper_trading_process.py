"""
PaperTradingRuntime — 纸上交易运行时编排器.

纯编排层：委托 BrokerGateway 执行订单，并从 BrokerGateway 读取账户状态。
不包含任何撮合、成交或账户记账逻辑。
"""

from __future__ import annotations

from ditto_execution.broker.contracts import BrokerGateway
from ditto_execution.orders.model import Order
from ditto_execution.orders.ticket import OrderTicket
from ditto_portfolio.accounting.account import AccountView

__all__ = ["PaperTradingRuntime"]


class PaperTradingRuntime:
    """
    纸上交易运行时 — 最小冒烟测试级别的订单执行编排器.

    职责仅限于：
    1. 提交订单到 BrokerGateway
    2. 返回 gateway 产出的订单状态
    3. 从 gateway 读取账户快照

    不实现任何撮合、定价或风控逻辑。
    """

    def __init__(self, gateway: BrokerGateway) -> None:
        self._gateway = gateway

    def execute_order(self, order: Order) -> OrderTicket:
        """
        执行订单：提交到 gateway，并由 gateway 拥有账户记账状态.

        Args:
            order: 待执行订单

        Returns:
            填充完成的 OrderTicket

        """
        ticket = self._gateway.submit_order(order)
        return ticket

    def get_account(self) -> AccountView:
        """返回 gateway 拥有的当前账户快照."""
        return self._gateway.get_account()
