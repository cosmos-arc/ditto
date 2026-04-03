"""Account / AccountView — 可变账户 + 只读快照。"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field, replace
from types import MappingProxyType

from ditto_kernel.enums import OrderSide
from ditto_kernel.identity import InstrumentId

from ditto_engine.accounting.cash import CashBook
from ditto_engine.accounting.fills import FillEvent
from ditto_engine.accounting.order_book import (
    OrderBook,
    OrderBookReadOnly,
)
from ditto_engine.accounting.position import Position

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

    positions: MappingProxyType[InstrumentId, Position]
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

    positions: dict[InstrumentId, Position] = field(default_factory=dict, init=False)
    _cash: CashBook = field(
        default_factory=lambda: CashBook(available=0.0, settled=0.0, frozen=0.0),
        init=False,
        repr=False,
    )
    order_book: OrderBook = field(default_factory=OrderBook, init=False)

    def __init__(
        self,
        positions: dict[InstrumentId, Position] | None = None,
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
            if ticket.order.direction == OrderSide.BUY:
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

    # -- fill application ----------------------------------------------------

    def apply_fill(
        self,
        fill: FillEvent,
        settle_date: str,
        *,
        on_frozen: Callable[[InstrumentId, str, int], None] | None = None,
    ) -> None:
        """
        应用成交事件，更新持仓和现金。

        从 BacktestBrokerage 提取的持仓/资金更新逻辑。
        BUY 时通过 on_frozen 回调注册冻结份额（T+1 交收），
        SELL 时扣减 available_quantity 并计算已实现盈亏。

        Args:
            fill: 成交事件
            settle_date: 交收日期 (YYYY-MM-DD)，用于冻结份额追踪
            on_frozen: 冻结回调，签名 (instrument_id, settle_date, quantity)。
                BUY 时调用，由 Brokerage 实现 T+1 冻结注册逻辑。

        """
        self._update_position_from_fill(fill, settle_date, on_frozen)
        self._update_cash_from_fill(fill)

    def _update_position_from_fill(
        self,
        fill: FillEvent,
        settle_date: str,
        on_frozen: Callable[[InstrumentId, str, int], None] | None,
    ) -> None:
        """更新持仓 — BUY 时注册冻结, SELL 时扣减 available_quantity。"""
        iid = fill.instrument_id
        existing = self.positions.get(iid)
        price = fill.fill_price
        qty = fill.filled_quantity

        if fill.direction == OrderSide.BUY:
            if existing is not None:
                total_qty = existing.quantity + qty
                avg_cost = (
                    existing.average_cost * existing.quantity + price * qty
                ) / total_qty
                new_pos = replace(
                    existing,
                    quantity=total_qty,
                    average_cost=avg_cost,
                    market_value=avg_cost * total_qty,
                    total_fees=existing.total_fees + fill.fee,
                )
            else:
                new_pos = Position(
                    instrument_id=iid,
                    quantity=qty,
                    available_quantity=0,
                    average_cost=price,
                    market_value=price * qty,
                    unrealized_pnl=0.0,
                    realized_pnl=0.0,
                    total_fees=fill.fee,
                )
            self.positions[iid] = new_pos
            # 注册冻结: settle_date 到期后解冻
            if on_frozen is not None:
                on_frozen(iid, settle_date, qty)

        elif fill.direction == OrderSide.SELL:
            if existing is not None:
                new_qty = existing.quantity - qty
                new_avail = existing.available_quantity - qty
                realized = (price - existing.average_cost) * qty
                if new_qty <= 0:
                    del self.positions[iid]
                else:
                    new_pos = replace(
                        existing,
                        quantity=new_qty,
                        available_quantity=new_avail,
                        market_value=existing.average_cost * new_qty,
                        realized_pnl=existing.realized_pnl + realized,
                        total_fees=existing.total_fees + fill.fee,
                    )
                    self.positions[iid] = new_pos

    def _update_cash_from_fill(self, fill: FillEvent) -> None:
        """更新现金。"""
        cash = self.cash
        price = fill.fill_price
        qty = fill.filled_quantity
        fee = fill.fee
        amount = price * qty

        if fill.direction == OrderSide.BUY:
            new_available = cash.available - amount - fee
            new_settled = cash.settled - fee
            self.cash = CashBook(
                available=new_available,
                settled=new_settled,
                frozen=cash.frozen,
            )
        elif fill.direction == OrderSide.SELL:
            new_available = cash.available + amount - fee
            new_settled = cash.settled + amount - fee
            self.cash = CashBook(
                available=new_available,
                settled=new_settled,
                frozen=cash.frozen,
            )
