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

    Attributes:
        positions: 持仓映射 (instrument_id -> Position)，只读代理
        cash: 现金账本快照
        total_value: 总资产 = cash.total + exposure
        nav: 净资产值 = cash.total + sum(market_value + unrealized_pnl)
        exposure: 持仓总市值 = sum(market_value)
        pending_buy_value: 未完成买入订单的预计金额
        order_book: 订单簿只读视图

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

    Note:
        cash 字段使用 property 封装，内部存储为 _cash。
        外部读写通过 account.cash / account.cash = ... 访问。

    """

    positions: dict[str, Position] = field(default_factory=dict, init=False)
    _cash: CashBook = field(
        default_factory=lambda: CashBook(available=0.0, settled=0.0, frozen=0.0),
        init=False,
        repr=False,
    )
    order_book: OrderBook = field(default_factory=OrderBook, init=False)

    def __init__(
        self,
        positions: dict[str, Position] | None = None,
        cash: CashBook | None = None,
        order_book: OrderBook | None = None,
    ) -> None:
        """
        初始化账户。

        Args:
            positions: 持仓映射
            cash: 现金账本
            order_book: 订单簿

        """
        # 绕过 dataclass 自动生成的 __init__，直接设置属性
        object.__setattr__(
            self,
            "positions",
            positions if positions is not None else {},
        )
        object.__setattr__(
            self,
            "_cash",
            cash
            if cash is not None
            else CashBook(
                available=0.0,
                settled=0.0,
                frozen=0.0,
            ),
        )
        object.__setattr__(
            self,
            "order_book",
            order_book if order_book is not None else OrderBook(),
        )

    @property
    def cash(self) -> CashBook:
        """获取现金账本。"""
        return self._cash

    @cash.setter
    def cash(self, value: CashBook) -> None:
        """设置现金账本（替换为新的 frozen 实例）。"""
        object.__setattr__(self, "_cash", value)

    def _calc_exposure(self) -> float:
        """计算持仓总市值 (exposure = sum(market_value))。"""
        return sum(p.market_value for p in self.positions.values())

    def _calc_pending_buy_value(self) -> float:
        """计算未完成买入订单的预计金额 (leaves_quantity * price)。"""
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
