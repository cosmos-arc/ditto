"""Account / AccountView — 可变账户 + 只读快照。"""

from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType

from ditto_core.accounting.cash import CashBook
from ditto_core.accounting.order_book import (
    OrderBook,
    OrderBookReadOnly,
    OrderDirection,
)
from ditto_core.accounting.position import Position

__all__ = ["Account", "AccountView"]


@dataclass(frozen=True)
class AccountView:
    """
    只读账户快照 — execution/risk/pipeline 通过它读取状态。

    所有字段均为 frozen / 只读引用，只读彻底闭环 (F5)。
    """

    positions: MappingProxyType[str, Position]
    cash: CashBook
    total_value: float
    nav: float
    exposure: float
    pending_buy_value: float
    order_book: OrderBookReadOnly


@dataclass
class Account:
    """
    可变账户状态 — state owner (Brokerage) 持有此实例。

    状态变更通过替换 frozen 引用实现（CashBook），
    或直接修改 dict（positions）。
    """

    positions: dict[str, Position] = field(default_factory=dict)
    cash: CashBook = field(
        default_factory=lambda: CashBook(available=0.0, settled=0.0, frozen=0.0),
    )
    order_book: OrderBook = field(default_factory=OrderBook)

    def _calc_nav(self) -> float:
        return self.cash.total + sum(
            p.market_value + p.unrealized_pnl for p in self.positions.values()
        )

    def _calc_exposure(self) -> float:
        return sum(p.market_value for p in self.positions.values())

    def _calc_pending_buy_value(self) -> float:
        total = 0.0
        for ticket in self.order_book.get_pending():
            if ticket.order.direction == OrderDirection.BUY:
                total += ticket.leaves_quantity * (ticket.order.price or 0.0)
        return total

    def get_view(self) -> AccountView:
        """生成只读账户快照。"""
        exposure = self._calc_exposure()
        return AccountView(
            positions=MappingProxyType(dict(self.positions)),
            cash=self.cash,
            total_value=self.cash.total + exposure,
            nav=self.cash.total
            + sum(p.market_value + p.unrealized_pnl for p in self.positions.values()),
            exposure=exposure,
            pending_buy_value=self._calc_pending_buy_value(),
            order_book=self.order_book.readonly_view(),
        )
