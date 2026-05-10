"""Account / AccountView — 可变账户 + 只读快照。"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field, replace
from types import MappingProxyType

from ditto_kernel.identity import InstrumentId
from ditto_kernel.order import OrderSide

from ditto_portfolio.accounting.cash import CashBook
from ditto_portfolio.accounting.fills import FillEvent
from ditto_portfolio.accounting.order_book import (
    OrderBook,
    OrderBookReadOnly,
)
from ditto_portfolio.accounting.position import Position

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

    _positions: dict[InstrumentId, Position] = field(default_factory=dict, init=False)
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
            "_positions",
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
    def positions(self) -> MappingProxyType[InstrumentId, Position]:
        """获取持仓的只读视图（外部不可直接修改）。"""
        return MappingProxyType(self._positions)

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
        return sum(p.market_value for p in self._positions.values())

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
            positions=MappingProxyType(dict(self._positions)),
            cash=self.cash,
            total_value=self.cash.total + exposure,
            nav=self.cash.total
            + sum(p.market_value + p.unrealized_pnl for p in self._positions.values()),
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
        应用成交事件，原子更新持仓和现金。

        从 BacktestBrokerage 提取的持仓/资金更新逻辑。
        BUY 时通过 on_frozen 回调注册冻结份额（T+1 交收），
        SELL 时扣减 available_quantity 并计算已实现盈亏。

        计算优先，原子赋值：先计算新的持仓状态和现金状态，
        再一次性赋值，避免部分更新导致状态不一致。

        Args:
            fill: 成交事件
            settle_date: 交收日期 (YYYY-MM-DD)，用于冻结份额追踪
            on_frozen: 冻结回调，签名 (instrument_id, settle_date, quantity)。
                BUY 时调用，由 Brokerage 实现 T+1 冻结注册逻辑。

        """
        # Calculate new state first (may raise) — no mutation yet
        position_updates = self._calculate_new_position(fill)
        new_cash = self._calculate_new_cash(fill)
        # Atomic assignment — both succeed or neither
        self._apply_position_updates(position_updates)
        object.__setattr__(self, "_cash", new_cash)
        # Fire callback after state is committed
        if fill.direction == OrderSide.BUY and on_frozen is not None:
            on_frozen(fill.instrument_id, settle_date, fill.filled_quantity)

    # -- calculation helpers (pure, no mutation) -----------------------------

    def _calculate_new_position(
        self,
        fill: FillEvent,
    ) -> dict[str, tuple[InstrumentId, Position | None]]:
        """
        计算成交后的持仓变更，返回待应用的更新列表。

        Returns:
            dict with key "upsert" for add/update or "remove" for delete.
            Each entry maps instrument_id to new Position (upsert) or None (remove).

        """
        iid = fill.instrument_id
        existing = self._positions.get(iid)
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
            return {"upsert": (iid, new_pos)}

        # SELL
        if existing is not None:
            new_qty = existing.quantity - qty
            new_avail = existing.available_quantity - qty
            realized = (price - existing.average_cost) * qty
            if new_qty <= 0:
                return {"remove": (iid, None)}
            new_pos = replace(
                existing,
                quantity=new_qty,
                available_quantity=new_avail,
                market_value=existing.average_cost * new_qty,
                realized_pnl=existing.realized_pnl + realized,
                total_fees=existing.total_fees + fill.fee,
            )
            return {"upsert": (iid, new_pos)}

        return {}

    def _apply_position_updates(
        self,
        updates: dict[str, tuple[InstrumentId, Position | None]],
    ) -> None:
        """将计算好的持仓变更应用到内部 dict。"""
        if "upsert" in updates:
            iid, pos = updates["upsert"]
            self._positions[iid] = pos  # type: ignore[assignment]
        elif "remove" in updates:
            iid = updates["remove"][0]
            self._positions.pop(iid, None)

    def _calculate_new_cash(self, fill: FillEvent) -> CashBook:
        """计算成交后的新现金状态（纯计算，无副作用）。"""
        cash = self._cash
        price = fill.fill_price
        qty = fill.filled_quantity
        fee = fill.fee
        amount = price * qty

        if fill.direction == OrderSide.BUY:
            return CashBook(
                available=cash.available - amount - fee,
                settled=cash.settled - fee,
                frozen=cash.frozen,
            )
        # SELL
        return CashBook(
            available=cash.available + amount - fee,
            settled=cash.settled + amount - fee,
            frozen=cash.frozen,
        )

    # -- thaw (解冻 available_quantity, 由 Brokerage 调用) -------------------

    def thaw_position(self, instrument_id: InstrumentId, quantity: int) -> None:
        """
        解冻持仓的 available_quantity — T+N 交收后由 Brokerage 调用.

        仅更新 available_quantity，不改变持仓数量/成本等字段。
        当仓位不存在时静默跳过（仓位已清空的边缘场景）。

        Args:
            instrument_id: 标的 ID
            quantity: 解冻数量

        """
        pos = self._positions.get(instrument_id)
        if pos is not None:
            self._positions[instrument_id] = replace(
                pos,
                available_quantity=pos.available_quantity + quantity,
            )
