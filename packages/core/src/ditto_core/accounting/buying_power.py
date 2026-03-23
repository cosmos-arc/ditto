"""BuyingPowerModel — 购买力模型 Protocol + 现金账户实现。"""

from __future__ import annotations

from typing import Protocol

from ditto_core.accounting.account import AccountView
from ditto_core.accounting.order_book import OrderDirection

__all__ = ["BuyingPowerModel", "CashAccountBuyingPower"]


class BuyingPowerModel(Protocol):
    """购买力模型 — 策略引擎通过此接口查询可用购买力。"""

    def available_buying_power(
        self,
        account: AccountView,
        direction: OrderDirection,
    ) -> float:
        """查询可用购买力。"""
        ...


class CashAccountBuyingPower:
    """
    V1: 现金多头账户。

    buying_power = cash.available（不含 frozen）。
    卖出不需要购买力 → 返回 0.0。
    """

    def available_buying_power(
        self,
        account: AccountView,
        direction: OrderDirection,
    ) -> float:
        """查询可用购买力。"""
        if direction == OrderDirection.SELL:
            return 0.0
        return account.cash.available
