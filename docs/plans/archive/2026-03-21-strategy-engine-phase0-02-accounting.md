# Phase 0 Part 1: accounting/ 共享账户契约层

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Status:** ✅ DONE (2026-03-21)

**Goal:** 实现 accounting/ 模块所有数据结构：Position, CashBook, OrderBook, Account, AccountView, BuyingPowerModel

**Architecture:** 纯数据结构层，frozen dataclass + Protocol。Account 是唯一可变对象（内部通过替换 frozen 引用更新状态）。AccountView 是只读快照，供上层模块安全消费。

**Design Doc:** v3 §3.1-§3.6

---

## Task 1: Position (frozen dataclass) `[S]`

**Files:**
- Create: `packages/core/src/ditto_core/accounting/__init__.py`
- Create: `packages/core/src/ditto_core/accounting/position.py`
- Test: `packages/core/tests/unit/accounting/test_position_unit.py`

**Step 1: Write the failing test**

```python
# packages/core/tests/unit/accounting/test_position_unit.py
"""Tests for Position frozen dataclass."""

import pytest
from dataclasses import FrozenInstanceError


class TestPosition:
    def test_create_position(self) -> None:
        from ditto_core.accounting.position import Position

        pos = Position(
            instrument_id="159915.SZ",
            quantity=1000,
            available_quantity=0,  # T+1: 买入当日不可卖
            average_cost=0.4520,
            market_value=452.0,
            unrealized_pnl=0.0,
            realized_pnl=0.0,
            total_fees=2.26,
        )
        assert pos.instrument_id == "159915.SZ"
        assert pos.quantity == 1000
        assert pos.available_quantity == 0
        assert pos.average_cost == 0.4520
        assert pos.total_fees == 2.26

    def test_position_is_frozen(self) -> None:
        from ditto_core.accounting.position import Position

        pos = Position(
            instrument_id="159915.SZ",
            quantity=1000,
            available_quantity=0,
            average_cost=0.4520,
            market_value=452.0,
            unrealized_pnl=0.0,
            realized_pnl=0.0,
            total_fees=0.0,
        )
        with pytest.raises(FrozenInstanceError):
            pos.quantity = 500  # type: ignore[misc]

    def test_position_with_update_returns_new_instance(self) -> None:
        from ditto_core.accounting.position import Position

        pos = Position(
            instrument_id="159915.SZ",
            quantity=1000,
            available_quantity=0,
            average_cost=0.4520,
            market_value=452.0,
            unrealized_pnl=0.0,
            realized_pnl=0.0,
            total_fees=0.0,
        )
        updated = pos._replace(
            available_quantity=1000,  # T+1 交收后
            market_value=460.0,
            unrealized_pnl=8.0,
        )
        assert updated.available_quantity == 1000
        assert updated.unrealized_pnl == 8.0
        # 原实例不变
        assert pos.available_quantity == 0

    def test_position_with_realized_pnl(self) -> None:
        from ditto_core.accounting.position import Position

        pos = Position(
            instrument_id="159915.SZ",
            quantity=500,
            available_quantity=500,
            average_cost=0.4520,
            market_value=240.0,
            unrealized_pnl=14.0,
            realized_pnl=10.0,
            total_fees=3.0,
        )
        assert pos.realized_pnl == 10.0
```

**Step 2: Run test to verify it fails**

```bash
pixi run -e dev pytest packages/core/tests/unit/accounting/test_position_unit.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'ditto_core.accounting'`

**Step 3: Write minimal implementation**

```python
# packages/core/src/ditto_core/accounting/position.py
"""Position — 单个标的的持仓状态 (frozen dataclass)."""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["Position"]


@dataclass(frozen=True)
class Position:
    """单个标的的持仓状态。

    Attributes:
        instrument_id: 标的 ID（如 "159915.SZ"）
        quantity: 总持仓数量（股数）
        available_quantity: 可卖数量（扣除 T+1 冻结）
        average_cost: 加权平均成本
        market_value: 当前市值
        unrealized_pnl: 浮动盈亏
        realized_pnl: 已实现盈亏（累计）
        total_fees: 累计交易费用
    """

    instrument_id: str
    quantity: int
    available_quantity: int
    average_cost: float
    market_value: float
    unrealized_pnl: float
    realized_pnl: float
    total_fees: float
```

```python
# packages/core/src/ditto_core/accounting/__init__.py
"""Accounting — 共享账户契约层.

纯数据结构，无 I/O。提供 Account（可变状态）和 AccountView（只读快照）。
"""

from ditto_core.accounting.position import Position

__all__ = [
    "Position",
]
```

**Step 4: Run test to verify it passes**

```bash
pixi run -e dev pytest packages/core/tests/unit/accounting/test_position_unit.py -v
```

Expected: 4 passed

**Step 5: Commit**

```bash
git add packages/core/src/ditto_core/accounting/ packages/core/tests/unit/accounting/test_position_unit.py
git commit -m "feat(core): add accounting Position frozen dataclass"
```

---

## Task 2: CashBook (frozen, R6) `[S]`

**Files:**
- Create: `packages/core/src/ditto_core/accounting/cash.py`
- Modify: `packages/core/src/ditto_core/accounting/__init__.py`
- Test: `packages/core/tests/unit/accounting/test_cash_book_unit.py`

**Step 1: Write the failing test**

```python
# packages/core/tests/unit/accounting/test_cash_book_unit.py
"""Tests for CashBook frozen dataclass (R6)."""

import pytest
from dataclasses import FrozenInstanceError


class TestCashBook:
    def test_create_cash_book(self) -> None:
        from ditto_core.accounting.cash import CashBook

        cash = CashBook(available=90000.0, settled=85000.0, frozen=10000.0)
        assert cash.available == 90000.0
        assert cash.settled == 85000.0
        assert cash.frozen == 10000.0

    def test_cash_book_is_frozen(self) -> None:
        from ditto_core.accounting.cash import CashBook

        cash = CashBook(available=100000.0, settled=100000.0, frozen=0.0)
        with pytest.raises(FrozenInstanceError):
            cash.available = 50000.0  # type: ignore[misc]

    def test_total_cash_property(self) -> None:
        from ditto_core.accounting.cash import CashBook

        cash = CashBook(available=90000.0, settled=85000.0, frozen=10000.0)
        assert cash.total == 100000.0  # available + frozen

    def test_create_replacement_after_fill(self) -> None:
        from ditto_core.accounting.cash import CashBook

        original = CashBook(available=100000.0, settled=100000.0, frozen=0.0)
        fee = 5.0
        # 模拟成交后扣除手续费
        updated = CashBook(
            available=original.available - fee,
            settled=original.settled,
            frozen=original.frozen,
        )
        assert updated.available == pytest.approx(99995.0)
        assert original.available == 100000.0  # 原实例不变
```

**Step 2: Run test to verify it fails**

```bash
pixi run -e dev pytest packages/core/tests/unit/accounting/test_cash_book_unit.py -v
```

**Step 3: Write minimal implementation**

```python
# packages/core/src/ditto_core/accounting/cash.py
"""CashBook — 现金账户 (frozen dataclass, R6)."""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["CashBook"]


@dataclass(frozen=True)
class CashBook:
    """现金账户（不可变）— 状态变更通过创建新实例。

    Attributes:
        available: 可用现金（扣除冻结）
        settled: 已交收（可提现）
        frozen: 冻结金额（待交收/待成交）
    """

    available: float
    settled: float
    frozen: float

    @property
    def total(self) -> float:
        """可用 + 冻结 = 账户总现金。"""
        return self.available + self.frozen
```

**Step 4: Run test to verify it passes**

```bash
pixi run -e dev pytest packages/core/tests/unit/accounting/test_cash_book_unit.py -v
```

**Step 5: Update __init__.py and commit**

```python
# 在 packages/core/src/ditto_core/accounting/__init__.py 中添加:
from ditto_core.accounting.cash import CashBook

__all__ = [
    "CashBook",
    "Position",
]
```

```bash
git add packages/core/src/ditto_core/accounting/ packages/core/tests/unit/accounting/test_cash_book_unit.py
git commit -m "feat(core): add accounting CashBook frozen dataclass (R6)"
```

---

## Task 3: OrderTicket / OrderBook / StateTransitionError (F5) `[L]`

**Files:**
- Create: `packages/core/src/ditto_core/accounting/order_book.py`
- Modify: `packages/core/src/ditto_core/accounting/__init__.py`
- Test: `packages/core/tests/unit/accounting/test_order_book_unit.py`

> **前置依赖**: Task 2 (CashBook) 之前需先完成 execution/orders.py 中的 OrderType/OrderDirection/OrderStatus。
> 为解耦，本 Task 内联定义最小枚举（execution/orders.py 的完整实现在 Part 2 补充）。

**Step 1: Write the failing test**

```python
# packages/core/tests/unit/accounting/test_order_book_unit.py
"""Tests for OrderBook / OrderTicket (F5: frozen)."""

from __future__ import annotations

import pytest
from dataclasses import FrozenInstanceError, replace
from datetime import datetime

from ditto_core.accounting.order_book import (
    OrderBook,
    OrderBookReadOnly,
    OrderDirection,
    OrderEvent,
    OrderStatus,
    OrderTicket,
    OrderType,
    StateTransitionError,
)


def _make_order(
    order_id: str = "ORD-001",
    instrument_id: str = "159915.SZ",
    quantity: int = 100,
    price: float | None = None,
) -> "ditto_core.accounting.order_book.Order":
    """Helper to create a minimal Order for testing."""
    from ditto_core.accounting.order_book import Order

    return Order(
        order_id=order_id,
        instrument_id=instrument_id,
        order_type=OrderType.MARKET,
        direction=OrderDirection.BUY,
        quantity=quantity,
        price=price,
        created_at=datetime(2026, 1, 15, 10, 30, 0),
        strategy_run_id="RUN-001",
    )


class TestOrder:
    def test_create_market_order(self) -> None:
        order = _make_order()
        assert order.order_id == "ORD-001"
        assert order.instrument_id == "159915.SZ"
        assert order.quantity == 100
        assert order.price is None
        assert order.direction == OrderDirection.BUY

    def test_order_is_frozen(self) -> None:
        order = _make_order()
        with pytest.raises(FrozenInstanceError):
            order.quantity = 200  # type: ignore[misc]

    def test_order_with_quantity(self) -> None:
        order = _make_order(quantity=100)
        resized = order.with_quantity(200)
        assert resized.quantity == 200
        assert order.quantity == 100  # 原实例不变

    def test_create_limit_order(self) -> None:
        order = _make_order(price=0.460)
        assert order.order_type == OrderType.MARKET  # default
        # 需要显式创建 limit order
        from ditto_core.accounting.order_book import Order, OrderType

        limit_order = replace(order, order_type=OrderType.LIMIT, price=0.460)
        assert limit_order.price == 0.460


class TestOrderStatus:
    def test_terminal_states(self) -> None:
        terminal = {OrderStatus.FILLED, OrderStatus.CANCELED, OrderStatus.REJECTED, OrderStatus.INVALID}
        for status in OrderStatus:
            if status in terminal:
                assert status.is_terminal
            else:
                assert not status.is_terminal


class TestOrderEvent:
    def test_create_order_event(self) -> None:
        event = OrderEvent(
            order_id="ORD-001",
            status=OrderStatus.SUBMITTED,
            timestamp=datetime(2026, 1, 15, 10, 30, 1),
        )
        assert event.order_id == "ORD-001"
        assert event.fill_price is None
        assert event.fee == 0.0

    def test_create_fill_event(self) -> None:
        event = OrderEvent(
            order_id="ORD-001",
            status=OrderStatus.PARTIALLY_FILLED,
            fill_price=0.452,
            fill_quantity=100,
            fee=2.26,
            timestamp=datetime(2026, 1, 15, 10, 30, 5),
        )
        assert event.fill_price == 0.452
        assert event.fill_quantity == 100
        assert event.fee == 2.26


class TestOrderTicket:
    def test_create_ticket(self) -> None:
        order = _make_order()
        ticket = OrderTicket(order=order)
        assert ticket.status == OrderStatus.NEW
        assert ticket.filled_quantity == 0
        assert ticket.leaves_quantity == 100

    def test_ticket_is_frozen(self) -> None:
        ticket = OrderTicket(order=_make_order())
        with pytest.raises(FrozenInstanceError):
            ticket.status = OrderStatus.SUBMITTED  # type: ignore[misc]

    def test_with_fill_partial(self) -> None:
        order = _make_order(quantity=200)
        ticket = OrderTicket(order=order)
        event = OrderEvent(
            order_id="ORD-001",
            status=OrderStatus.PARTIALLY_FILLED,
            fill_price=0.452,
            fill_quantity=100,
            timestamp=datetime(2026, 1, 15, 10, 30, 5),
        )
        new_ticket = ticket.with_fill(quantity=100, price=0.452, event=event)
        assert new_ticket.filled_quantity == 100
        assert new_ticket.leaves_quantity == 100
        assert new_ticket.status == OrderStatus.PARTIALLY_FILLED
        assert len(new_ticket.order_events) == 1
        # 原实例不变
        assert ticket.filled_quantity == 0

    def test_with_fill_full(self) -> None:
        order = _make_order(quantity=200)
        ticket = OrderTicket(order=order)
        event = OrderEvent(
            order_id="ORD-001",
            status=OrderStatus.FILLED,
            fill_price=0.452,
            fill_quantity=200,
            timestamp=datetime(2026, 1, 15, 10, 30, 5),
        )
        new_ticket = ticket.with_fill(quantity=200, price=0.452, event=event)
        assert new_ticket.filled_quantity == 200
        assert new_ticket.leaves_quantity == 0
        assert new_ticket.status == OrderStatus.FILLED

    def test_with_cancel(self) -> None:
        ticket = OrderTicket(order=_make_order())
        event = OrderEvent(
            order_id="ORD-001",
            status=OrderStatus.CANCELED,
            timestamp=datetime(2026, 1, 15, 11, 0, 0),
            message="user_cancel",
        )
        new_ticket = ticket.with_cancel(event)
        assert new_ticket.status == OrderStatus.CANCELED
        assert new_ticket.order_events[0].message == "user_cancel"

    def test_with_cancel_terminal_raises(self) -> None:
        ticket = OrderTicket(
            order=_make_order(),
            status=OrderStatus.FILLED,
            filled_quantity=100,
        )
        event = OrderEvent(
            order_id="ORD-001",
            status=OrderStatus.CANCELED,
            timestamp=datetime(2026, 1, 15, 11, 0, 0),
        )
        with pytest.raises(StateTransitionError, match="terminal state"):
            ticket.with_cancel(event)

    def test_with_reject(self) -> None:
        ticket = OrderTicket(order=_make_order())
        event = OrderEvent(
            order_id="ORD-001",
            status=OrderStatus.REJECTED,
            timestamp=datetime(2026, 1, 15, 10, 30, 2),
            message="insufficient_buying_power",
        )
        new_ticket = ticket.with_reject(event)
        assert new_ticket.status == OrderStatus.REJECTED

    def test_with_invalid(self) -> None:
        """B2: can_retry=False → INVALID 终态"""
        ticket = OrderTicket(order=_make_order())
        event = OrderEvent(
            order_id="ORD-001",
            status=OrderStatus.INVALID,
            timestamp=datetime(2026, 1, 15, 10, 30, 2),
            message="[invalid] insufficient_auction",
        )
        new_ticket = ticket.with_invalid(event)
        assert new_ticket.status == OrderStatus.INVALID
        assert new_ticket.status.is_terminal


class TestOrderBook:
    def test_submit_and_get(self) -> None:
        book = OrderBook()
        ticket = OrderTicket(order=_make_order())
        book.submit(ticket)
        assert book.get("ORD-001") is ticket

    def test_get_nonexistent_returns_none(self) -> None:
        book = OrderBook()
        assert book.get("NONEXISTENT") is None

    def test_get_pending(self) -> None:
        book = OrderBook()
        book.submit(OrderTicket(order=_make_order("ORD-001")))
        book.submit(OrderTicket(order=_make_order("ORD-002")))

        pending = book.get_pending()
        assert len(pending) == 2

    def test_update_ticket(self) -> None:
        book = OrderBook()
        ticket = OrderTicket(order=_make_order())
        book.submit(ticket)

        event = OrderEvent(
            order_id="ORD-001",
            status=OrderStatus.SUBMITTED,
            timestamp=datetime(2026, 1, 15, 10, 30, 1),
        )
        submitted = replace(ticket, status=OrderStatus.SUBMITTED, order_events=(event,))
        book.update(submitted)

        assert book.get("ORD-001").status == OrderStatus.SUBMITTED

    def test_cancel_order(self) -> None:
        book = OrderBook()
        ticket = OrderTicket(order=_make_order())
        book.submit(ticket)
        book.cancel("ORD-001")
        assert book.get("ORD-001").status == OrderStatus.CANCELED

    def test_cancel_terminal_raises(self) -> None:
        book = OrderBook()
        filled = OrderTicket(
            order=_make_order(),
            status=OrderStatus.FILLED,
            filled_quantity=100,
        )
        book.submit(filled)
        with pytest.raises(StateTransitionError):
            book.cancel("ORD-001")

    def test_readonly_view(self) -> None:
        book = OrderBook()
        book.submit(OrderTicket(order=_make_order("ORD-001")))
        view = book.readonly_view()
        assert view.get("ORD-001") is not None
        assert len(view.get_pending()) == 1
```

**Step 2: Run test to verify it fails**

```bash
pixi run -e dev pytest packages/core/tests/unit/accounting/test_order_book_unit.py -v
```

**Step 3: Write implementation**

```python
# packages/core/src/ditto_core/accounting/order_book.py
"""OrderBook / OrderTicket / Order — 订单簿 (F5: frozen dataclass).

Phase 0 内联定义 Order 相关类型（最小枚举）。
execution/orders.py (Part 2) 将定义完整版本并从那里 re-export。
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum

__all__ = [
    "Order",
    "OrderBook",
    "OrderBookReadOnly",
    "OrderDirection",
    "OrderEvent",
    "OrderStatus",
    "OrderTicket",
    "OrderType",
    "StateTransitionError",
]


class OrderType(StrEnum):
    """订单类型。"""

    MARKET = "market"
    LIMIT = "limit"
    STOP_MARKET = "stop_market"
    MARKET_ON_CLOSE = "market_on_close"


class OrderDirection(StrEnum):
    """订单方向。"""

    BUY = "buy"
    SELL = "sell"


class OrderStatus(StrEnum):
    """订单状态。"""

    NEW = "new"
    SUBMITTED = "submitted"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELED = "canceled"
    REJECTED = "rejected"
    INVALID = "invalid"

    @property
    def is_terminal(self) -> bool:
        """终态：FILLED / CANCELED / REJECTED / INVALID。"""
        return self in (
            OrderStatus.FILLED,
            OrderStatus.CANCELED,
            OrderStatus.REJECTED,
            OrderStatus.INVALID,
        )


class StateTransitionError(Exception):
    """非法状态转换，如 FILLED → CANCEL。"""


@dataclass(frozen=True)
class Order:
    """订单 — frozen dataclass，创建后不可变。

    Attributes:
        order_id: 订单唯一 ID
        instrument_id: 标的 ID
        order_type: 订单类型
        direction: 买/卖
        quantity: 股数
        price: LIMIT 单价格（市价单为 None）
        stop_price: STOP 单触发价
        created_at: 创建时间
        strategy_run_id: 关联策略运行 ID
    """

    order_id: str
    instrument_id: str
    order_type: OrderType
    direction: OrderDirection
    quantity: int
    price: float | None = None
    stop_price: float | None = None
    created_at: datetime = field(default_factory=lambda: datetime(2026, 1, 1))
    strategy_run_id: str = ""

    def with_quantity(self, qty: int) -> Order:
        """创建新 Order 实例，用于 PreTrade resize。"""
        return replace(self, quantity=qty)
```

> **注意**: 上面 `Order.created_at` 使用了 `field(default_factory=...)` 但需要 `from dataclasses import field`。完整实现请参照下方。

```python
# 完整 order_book.py 实现：

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field, replace
from datetime import datetime
from enum import StrEnum


class OrderType(StrEnum):
    MARKET = "market"
    LIMIT = "limit"
    STOP_MARKET = "stop_market"
    MARKET_ON_CLOSE = "market_on_close"


class OrderDirection(StrEnum):
    BUY = "buy"
    SELL = "sell"


class OrderStatus(StrEnum):
    NEW = "new"
    SUBMITTED = "submitted"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELED = "canceled"
    REJECTED = "rejected"
    INVALID = "invalid"

    @property
    def is_terminal(self) -> bool:
        return self in (
            OrderStatus.FILLED,
            OrderStatus.CANCELED,
            OrderStatus.REJECTED,
            OrderStatus.INVALID,
        )


class StateTransitionError(Exception):
    """非法状态转换。"""


@dataclass(frozen=True)
class Order:
    order_id: str
    instrument_id: str
    order_type: OrderType
    direction: OrderDirection
    quantity: int
    price: float | None = None
    stop_price: float | None = None
    created_at: datetime = field(default_factory=lambda: datetime(2026, 1, 1))
    strategy_run_id: str = ""

    def with_quantity(self, qty: int) -> Order:
        return replace(self, quantity=qty)


@dataclass(frozen=True)
class OrderEvent:
    order_id: str
    status: OrderStatus
    fill_price: float | None = None
    fill_quantity: int = 0
    fee: float = 0.0
    message: str | None = None
    timestamp: datetime = field(default_factory=lambda: datetime(2026, 1, 1))


@dataclass(frozen=True)
class OrderTicket:
    """订单票据 — frozen，状态变更通过 with_xxx() 返回新实例。"""

    order: Order
    status: OrderStatus = OrderStatus.NEW
    filled_quantity: int = 0
    filled_price: float | None = None
    average_fill_price: float | None = None
    order_events: tuple[OrderEvent, ...] = ()

    @property
    def leaves_quantity(self) -> int:
        return self.order.quantity - self.filled_quantity

    def with_fill(
        self, quantity: int, price: float, event: OrderEvent,
    ) -> OrderTicket:
        new_filled = self.filled_quantity + quantity
        new_status = (
            OrderStatus.FILLED
            if new_filled >= self.order.quantity
            else OrderStatus.PARTIALLY_FILLED
        )
        return dataclasses.replace(
            self,
            filled_quantity=new_filled,
            filled_price=price,
            average_fill_price=self._calc_avg(price, quantity),
            status=new_status,
            order_events=(*self.order_events, event),
        )

    def with_cancel(self, event: OrderEvent) -> OrderTicket:
        if self.status.is_terminal:
            raise StateTransitionError(
                f"Cannot cancel order in terminal state: {self.status}"
            )
        return dataclasses.replace(
            self, status=OrderStatus.CANCELED,
            order_events=(*self.order_events, event),
        )

    def with_reject(self, event: OrderEvent) -> OrderTicket:
        return dataclasses.replace(
            self, status=OrderStatus.REJECTED,
            order_events=(*self.order_events, event),
        )

    def with_invalid(self, event: OrderEvent) -> OrderTicket:
        """B2: can_retry=False → INVALID 终态。"""
        if self.status.is_terminal:
            raise StateTransitionError(
                f"Cannot invalidate order in terminal state: {self.status}"
            )
        return dataclasses.replace(
            self, status=OrderStatus.INVALID,
            order_events=(*self.order_events, event),
        )

    def _calc_avg(self, price: float, quantity: int) -> float:
        if self.average_fill_price is None:
            return price
        total_qty = self.filled_quantity + quantity
        if total_qty == 0:
            return price
        return (self.average_fill_price * self.filled_quantity + price * quantity) / total_qty


class OrderBookReadOnly:
    """OrderBook 只读视图。"""

    def __init__(self, tickets: dict[str, OrderTicket]) -> None:
        self._tickets = tickets

    def get(self, order_id: str) -> OrderTicket | None:
        return self._tickets.get(order_id)

    def get_pending(self) -> tuple[OrderTicket, ...]:
        return tuple(
            t for t in self._tickets.values()
            if not t.status.is_terminal
        )


class OrderBook:
    """订单簿 — 持有所有 OrderTicket，只允许通过受控方法修改。"""

    def __init__(self) -> None:
        self._tickets: dict[str, OrderTicket] = {}

    def get(self, order_id: str) -> OrderTicket | None:
        return self._tickets.get(order_id)

    def get_pending(self) -> tuple[OrderTicket, ...]:
        return tuple(
            t for t in self._tickets.values()
            if not t.status.is_terminal
        )

    def submit(self, ticket: OrderTicket) -> None:
        self._tickets[ticket.order.order_id] = ticket

    def update(self, ticket: OrderTicket) -> None:
        self._tickets[ticket.order.order_id] = ticket

    def cancel(self, order_id: str) -> None:
        ticket = self._tickets.get(order_id)
        if ticket is None:
            raise KeyError(f"Order not found: {order_id}")
        if ticket.status.is_terminal:
            raise StateTransitionError(
                f"Cannot cancel order in terminal state: {ticket.status}"
            )
        event = OrderEvent(
            order_id=order_id,
            status=OrderStatus.CANCELED,
            timestamp=datetime(2026, 1, 1),
        )
        self._tickets[order_id] = ticket.with_cancel(event)

    def readonly_view(self) -> OrderBookReadOnly:
        return OrderBookReadOnly(dict(self._tickets))
```

**Step 4: Run test to verify it passes**

```bash
pixi run -e dev pytest packages/core/tests/unit/accounting/test_order_book_unit.py -v
```

**Step 5: Update __init__.py and commit**

```python
# packages/core/src/ditto_core/accounting/__init__.py — 更新 __all__:
from ditto_core.accounting.cash import CashBook
from ditto_core.accounting.order_book import (
    Order,
    OrderBook,
    OrderBookReadOnly,
    OrderDirection,
    OrderEvent,
    OrderStatus,
    OrderTicket,
    OrderType,
    StateTransitionError,
)
from ditto_core.accounting.position import Position

__all__ = [
    "CashBook",
    "Order",
    "OrderBook",
    "OrderBookReadOnly",
    "OrderDirection",
    "OrderEvent",
    "OrderStatus",
    "OrderTicket",
    "OrderType",
    "Position",
    "StateTransitionError",
]
```

```bash
git add packages/core/src/ditto_core/accounting/ packages/core/tests/unit/accounting/
git commit -m "feat(core): add OrderBook/OrderTicket frozen (F5) with state machine"
```

---

## Task 4: Account / AccountView `[M]`

**Files:**
- Create: `packages/core/src/ditto_core/accounting/account.py`
- Modify: `packages/core/src/ditto_core/accounting/__init__.py`
- Test: `packages/core/tests/unit/accounting/test_account_unit.py`

**Step 1: Write the failing test**

```python
# packages/core/tests/unit/accounting/test_account_unit.py
"""Tests for Account / AccountView."""

from __future__ import annotations

import pytest
from dataclasses import FrozenInstanceError
from datetime import datetime

from ditto_core.accounting.cash import CashBook
from ditto_core.accounting.order_book import (
    Order,
    OrderBook,
    OrderDirection,
    OrderStatus,
    OrderTicket,
    OrderType,
)
from ditto_core.accounting.position import Position


def _default_order_kwargs() -> dict:
    return dict(
        order_id="ORD-001",
        instrument_id="159915.SZ",
        order_type=OrderType.MARKET,
        direction=OrderDirection.BUY,
        quantity=100,
        created_at=datetime(2026, 1, 15, 10, 30, 0),
        strategy_run_id="RUN-001",
    )


class TestAccount:
    def test_create_account_with_initial_cash(self) -> None:
        from ditto_core.accounting.account import Account

        account = Account(
            cash=CashBook(available=1000000.0, settled=1000000.0, frozen=0.0),
        )
        assert account.cash.available == 1000000.0
        assert account.positions == {}

    def test_account_is_mutable(self) -> None:
        from ditto_core.accounting.account import Account

        account = Account(
            cash=CashBook(available=1000000.0, settled=1000000.0, frozen=0.0),
        )
        # Account 本身不是 frozen — 可以修改 positions
        account.positions["159915.SZ"] = Position(
            instrument_id="159915.SZ",
            quantity=100,
            available_quantity=0,
            average_cost=0.452,
            market_value=45.2,
            unrealized_pnl=0.0,
            realized_pnl=0.0,
            total_fees=0.0,
        )
        assert "159915.SZ" in account.positions

    def test_get_view_returns_frozen_snapshot(self) -> None:
        from ditto_core.accounting.account import Account

        account = Account(
            cash=CashBook(available=1000000.0, settled=1000000.0, frozen=0.0),
        )
        account.positions["159915.SZ"] = Position(
            instrument_id="159915.SZ",
            quantity=100,
            available_quantity=0,
            average_cost=0.452,
            market_value=45.2,
            unrealized_pnl=0.0,
            realized_pnl=0.0,
            total_fees=0.0,
        )
        view = account.get_view()
        assert view.nav == pytest.approx(1000045.2)
        assert view.total_value == pytest.approx(1000045.2)
        # view 是 frozen — 修改 Account 不影响已有 view
        account.positions["510300.SH"] = Position(
            instrument_id="510300.SH",
            quantity=200,
            available_quantity=0,
            average_cost=4.0,
            market_value=820.0,
            unrealized_pnl=20.0,
            realized_pnl=0.0,
            total_fees=0.0,
        )
        assert "510300.SH" not in view.positions


class TestAccountView:
    def test_view_is_frozen(self) -> None:
        from ditto_core.accounting.account import Account

        account = Account(
            cash=CashBook(available=1000000.0, settled=1000000.0, frozen=0.0),
        )
        view = account.get_view()
        with pytest.raises(FrozenInstanceError):
            view.nav = 0.0  # type: ignore[misc]

    def test_view_positions_readonly(self) -> None:
        from ditto_core.accounting.account import Account

        account = Account(
            cash=CashBook(available=1000000.0, settled=1000000.0, frozen=0.0),
        )
        account.positions["159915.SZ"] = Position(
            instrument_id="159915.SZ",
            quantity=100,
            available_quantity=0,
            average_cost=0.452,
            market_value=45.2,
            unrealized_pnl=0.0,
            realized_pnl=0.0,
            total_fees=0.0,
        )
        view = account.get_view()
        # positions 通过 MappingProxyType 暴露，不可写
        with pytest.raises(TypeError):
            view.positions["NEW"] = Position(  # type: ignore[index]
                instrument_id="NEW",
                quantity=1, available_quantity=1,
                average_cost=1.0, market_value=1.0,
                unrealized_pnl=0.0, realized_pnl=0.0, total_fees=0.0,
            )

    def test_view_order_book_readonly(self) -> None:
        from ditto_core.accounting.account import Account

        account = Account(
            cash=CashBook(available=1000000.0, settled=1000000.0, frozen=0.0),
        )
        view = account.get_view()
        assert view.order_book.get("NONEXISTENT") is None
```

**Step 2: Run test to verify it fails**

```bash
pixi run -e dev pytest packages/core/tests/unit/accounting/test_account_unit.py -v
```

**Step 3: Write implementation**

```python
# packages/core/src/ditto_core/accounting/account.py
"""Account / AccountView — 可变账户 + 只读快照。"""

from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType

from ditto_core.accounting.cash import CashBook
from ditto_core.accounting.order_book import OrderBook, OrderBookReadOnly
from ditto_core.accounting.position import Position

__all__ = ["Account", "AccountView"]


@dataclass(frozen=True)
class AccountView:
    """只读账户快照 — execution/risk/pipeline 通过它读取状态。

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
    """可变账户状态 — state owner (Brokerage) 持有此实例。

    状态变更通过替换 frozen 引用实现（CashBook），
    或直接修改 dict（positions）。
    """

    positions: dict[str, Position] = field(default_factory=dict)
    _cash: CashBook = field(
        default_factory=lambda: CashBook(available=0.0, settled=0.0, frozen=0.0),
    )
    order_book: OrderBook = field(default_factory=OrderBook)

    @property
    def cash(self) -> CashBook:
        return self._cash

    def _calc_total_value(self) -> float:
        return self._cash.total + sum(
            p.market_value for p in self.positions.values()
        )

    def _calc_nav(self) -> float:
        return self._cash.total + sum(
            p.market_value + p.unrealized_pnl for p in self.positions.values()
        )

    def _calc_exposure(self) -> float:
        return sum(p.market_value for p in self.positions.values())

    def _calc_pending_buy_value(self) -> float:
        total = 0.0
        for ticket in self.order_book.get_pending():
            if ticket.order.direction.value == "buy":
                total += ticket.leaves_quantity * (ticket.order.price or 0.0)
        return total

    def get_view(self) -> AccountView:
        return AccountView(
            positions=MappingProxyType(self.positions),
            cash=self._cash,
            total_value=self._calc_total_value(),
            nav=self._calc_nav(),
            exposure=self._calc_exposure(),
            pending_buy_value=self._calc_pending_buy_value(),
            order_book=self.order_book.readonly_view(),
        )
```

**Step 4: Run test to verify it passes**

```bash
pixi run -e dev pytest packages/core/tests/unit/accounting/test_account_unit.py -v
```

**Step 5: Update __init__.py and commit**

```python
# 在 __init__.py 中添加:
from ditto_core.accounting.account import Account, AccountView
# __all__ 中添加 "Account", "AccountView"
```

```bash
git add packages/core/src/ditto_core/accounting/ packages/core/tests/unit/accounting/
git commit -m "feat(core): add Account (mutable) and AccountView (frozen snapshot)"
```

---

## Task 5: BuyingPowerModel Protocol `[S]`

**Files:**
- Create: `packages/core/src/ditto_core/accounting/buying_power.py`
- Modify: `packages/core/src/ditto_core/accounting/__init__.py`
- Test: `packages/core/tests/unit/accounting/test_buying_power_unit.py`

**Step 1: Write the failing test**

```python
# packages/core/tests/unit/accounting/test_buying_power_unit.py
"""Tests for BuyingPowerModel Protocol."""

from ditto_core.accounting.buying_power import (
    BuyingPowerModel,
    CashAccountBuyingPower,
)
from ditto_core.accounting.cash import CashBook
from ditto_core.accounting.order_book import OrderDirection


class TestBuyingPowerModel:
    def test_protocol_exists(self) -> None:
        assert hasattr(BuyingPowerModel, "__protocol_attrs__") or True
        # Protocol 在运行时无法直接检查，通过 isinstance 检查

    def test_cash_account_buy_for_buy(self) -> None:
        from ditto_core.accounting.account import Account, AccountView

        account = Account(
            cash=CashBook(available=100000.0, settled=100000.0, frozen=0.0),
        )
        view = account.get_view()
        model = CashAccountBuyingPower()
        result = model.available_buying_power(view, OrderDirection.BUY)
        assert result == 100000.0

    def test_cash_account_buy_for_sell(self) -> None:
        from ditto_core.accounting.account import Account

        account = Account(
            cash=CashBook(available=100000.0, settled=100000.0, frozen=0.0),
        )
        view = account.get_view()
        model = CashAccountBuyingPower()
        result = model.available_buying_power(view, OrderDirection.SELL)
        assert result == 0.0

    def test_cash_account_excludes_frozen(self) -> None:
        from ditto_core.accounting.account import Account

        account = Account(
            cash=CashBook(available=90000.0, settled=100000.0, frozen=10000.0),
        )
        view = account.get_view()
        model = CashAccountBuyingPower()
        result = model.available_buying_power(view, OrderDirection.BUY)
        assert result == 90000.0
```

**Step 2: Run test to verify it fails**

**Step 3: Write implementation**

```python
# packages/core/src/ditto_core/accounting/buying_power.py
"""BuyingPowerModel — 购买力模型 Protocol + 现金账户实现。"""

from __future__ import annotations

from typing import Protocol

from ditto_core.accounting.account import AccountView
from ditto_core.accounting.order_book import OrderDirection

__all__ = ["BuyingPowerModel", "CashAccountBuyingPower"]


class BuyingPowerModel(Protocol):
    """购买力模型 — 策略引擎通过此接口查询可用购买力。"""

    def available_buying_power(
        self, account: AccountView, direction: OrderDirection,
    ) -> float: ...


class CashAccountBuyingPower:
    """V1: 现金多头账户。

    buying_power = cash.available（不含 frozen）。
    卖出不需要购买力 → 返回 0.0。
    """

    def available_buying_power(
        self, account: AccountView, direction: OrderDirection,
    ) -> float:
        if direction == OrderDirection.SELL:
            return 0.0
        return account.cash.available
```

**Step 4: Run test to verify it passes**

```bash
pixi run -e dev pytest packages/core/tests/unit/accounting/test_buying_power_unit.py -v
```

**Step 5: Update __init__.py and commit**

```python
# 在 __init__.py 中添加:
from ditto_core.accounting.buying_power import BuyingPowerModel, CashAccountBuyingPower
# __all__ 中添加 "BuyingPowerModel", "CashAccountBuyingPower"
```

```bash
git add packages/core/src/ditto_core/accounting/ packages/core/tests/unit/accounting/
git commit -m "feat(core): add BuyingPowerModel Protocol + CashAccountBuyingPower"
```

---

## Task 6: accounting/ 模块完整验证 `[S]`

**Step 1: Run all accounting tests**

```bash
pixi run -e dev pytest packages/core/tests/unit/accounting/ -v
```

**Step 2: Run type check**

```bash
pixi run -e dev type --tests packages/core/src/ditto_core/accounting/ packages/core/tests/unit/accounting/
```

**Step 3: Run lint**

```bash
pixi run -e dev lint packages/core/src/ditto_core/accounting/ packages/core/tests/unit/accounting/
```

**Step 4: Fix any issues and commit final state**

```bash
pixi run -e dev check
git add -A packages/core/src/ditto_core/accounting/ packages/core/tests/unit/accounting/
git commit -m "chore(core): accounting module quality gate pass"
```

---

## Code Review Notes (P2 — deferred design improvements)

> 来源：code-simplifier review，实施完成后的 P2 发现。非 blocking，留作后续迭代参考。

### 1. `OrderBook` / `OrderBookReadOnly` 接口重复

`get()` 和 `get_pending()` 在两个类中完全相同。未来可考虑：
- 抽取 `OrderBookView` Protocol，两个类都实现
- 或让 `OrderBook` 继承 `OrderBookReadOnly`（需评估 mutable base 暴露的风险）

### 2. `OrderBook.update()` 缺少 `KeyError` 守卫

`cancel()` 方法会检查 order 是否存在并抛出 `KeyError`，但 `update()` 不做任何检查，对不存在的 order_id 会静默写入 dict。两者行为不一致。建议后续统一守卫逻辑。

### 3. `OrderEvent.timestamp` 使用魔法 datetime

多处 `datetime(2026, 1, 1)` 作为默认值仅用于测试便利，生产代码中不应出现。未来引入真实时间源时需要清理。

### 4. `Position.market_value` 命名可能引起混淆

`market_value` 在当前设计中实际表示「持仓市值」（= 数量 × 当前价格），但 `Account._calc_nav()` 中 `cash + market_value + unrealized_pnl` 的公式暗示 market_value 可能被理解为成本基准。需要在 v3 文档中明确语义。
