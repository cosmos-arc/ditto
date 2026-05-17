"""
Risk domain contracts — PreTrade 解耦 Protocol.

将 Risk 对 Execution (Order / OrderTicket) 的直接依赖
替换为本地 Protocol 抽象，使 Risk 不再 import ditto_execution。
"""

# ruff: noqa: D102 — Protocol stubs don't need docstrings

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ditto_kernel.identity import InstrumentId
from ditto_kernel.order import OrderSide, OrderType

__all__ = [
    "PreTradeOrder",
    "PreTradeTicket",
]


@runtime_checkable
class PreTradeOrder(Protocol):
    """订单抽象 — Risk 风控校验所需的只读订单接口。"""

    @property
    def instrument_id(self) -> InstrumentId: ...

    @property
    def quantity(self) -> int: ...

    @property
    def direction(self) -> OrderSide: ...

    @property
    def order_id(self) -> str: ...

    @property
    def order_type(self) -> OrderType: ...

    @property
    def price(self) -> float | None: ...

    def with_quantity(self, qty: int) -> PreTradeOrder: ...


@runtime_checkable
class PreTradeTicket(Protocol):
    """订单票据抽象 — Risk 风控校验所需的只读票据接口。"""

    @property
    def order(self) -> PreTradeOrder: ...

    @property
    def leaves_quantity(self) -> int: ...
