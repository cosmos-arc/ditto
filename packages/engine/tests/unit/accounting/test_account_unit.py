"""Tests for Account / AccountView."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import datetime

import pytest
from ditto_engine.accounting.account import Account
from ditto_engine.accounting.cash import CashBook
from ditto_engine.accounting.fills import FillEvent
from ditto_engine.accounting.position import Position
from ditto_kernel.order import OrderSide

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_fill(
    instrument_id: int = 1,
    direction: OrderSide = OrderSide.BUY,
    filled_quantity: int = 1000,
    fill_price: float = 10.5,
    fee: float = 5.0,
    slippage: float = 0.0,
    fill_id: str = "fill-1",
    order_id: str = "ORD-001",
) -> FillEvent:
    """创建测试用 FillEvent。"""
    return FillEvent(
        fill_id=fill_id,
        order_id=order_id,
        instrument_id=instrument_id,
        direction=direction,
        filled_quantity=filled_quantity,
        fill_price=fill_price,
        fee=fee,
        slippage=slippage,
        event_time=datetime(2026, 3, 1, 15, 0),
        cumulative_quantity=filled_quantity,
        leaves_quantity=0,
    )


def _make_account(
    cash: float = 1_000_000.0,
    positions: dict[int, Position] | None = None,
) -> Account:
    """创建测试用 Account。"""
    return Account(
        cash=CashBook(available=cash, settled=cash, frozen=0.0),
        positions=positions,
    )


# ---------------------------------------------------------------------------
# TestAccount (existing)
# ---------------------------------------------------------------------------


class TestAccount:
    def test_create_account_with_initial_cash(self) -> None:
        account = Account(
            cash=CashBook(available=1000000.0, settled=1000000.0, frozen=0.0),
        )
        assert account.cash.available == 1000000.0
        assert account.positions == {}

    def test_account_is_mutable(self) -> None:
        account = Account(
            cash=CashBook(available=1000000.0, settled=1000000.0, frozen=0.0),
        )
        # Account 本身不是 frozen — 可以修改 positions
        account.positions[1] = Position(
            instrument_id=1,
            quantity=100,
            available_quantity=0,
            average_cost=0.452,
            market_value=45.2,
            unrealized_pnl=0.0,
            realized_pnl=0.0,
            total_fees=0.0,
        )
        assert 1 in account.positions

    def test_get_view_returns_frozen_snapshot(self) -> None:
        account = Account(
            cash=CashBook(available=1000000.0, settled=1000000.0, frozen=0.0),
        )
        account.positions[1] = Position(
            instrument_id=1,
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
        account.positions[2] = Position(
            instrument_id=2,
            quantity=200,
            available_quantity=0,
            average_cost=4.0,
            market_value=820.0,
            unrealized_pnl=20.0,
            realized_pnl=0.0,
            total_fees=0.0,
        )
        assert 2 not in view.positions


# ---------------------------------------------------------------------------
# TestAccountView (existing)
# ---------------------------------------------------------------------------


class TestAccountView:
    def test_view_is_frozen(self) -> None:
        account = Account(
            cash=CashBook(available=1000000.0, settled=1000000.0, frozen=0.0),
        )
        view = account.get_view()
        with pytest.raises(FrozenInstanceError):
            view.nav = 0.0  # type: ignore[misc]

    def test_view_positions_readonly(self) -> None:
        account = Account(
            cash=CashBook(available=1000000.0, settled=1000000.0, frozen=0.0),
        )
        account.positions[1] = Position(
            instrument_id=1,
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
            view.positions[99] = Position(  # type: ignore[index]
                instrument_id=99,
                quantity=1,
                available_quantity=1,
                average_cost=1.0,
                market_value=1.0,
                unrealized_pnl=0.0,
                realized_pnl=0.0,
                total_fees=0.0,
            )

    def test_view_order_book_readonly(self) -> None:
        account = Account(
            cash=CashBook(available=1000000.0, settled=1000000.0, frozen=0.0),
        )
        view = account.get_view()
        assert view.order_book.get("NONEXISTENT") is None


# ---------------------------------------------------------------------------
# TestAccountApplyFill
# ---------------------------------------------------------------------------


class TestAccountApplyFillBuy:
    """apply_fill BUY 场景。"""

    def test_buy_creates_new_position(self) -> None:
        """BUY: 新建仓位, quantity 和 average_cost 正确。"""
        account = _make_account()
        fill = _make_fill(filled_quantity=1000, fill_price=10.5, fee=5.0)

        account.apply_fill(fill, settle_date="2026-03-02")

        assert 1 in account.positions
        pos = account.positions[1]
        assert pos.quantity == 1000
        assert pos.available_quantity == 0
        assert pos.average_cost == pytest.approx(10.5)
        assert pos.market_value == pytest.approx(10.5 * 1000)
        assert pos.total_fees == pytest.approx(5.0)
        assert pos.realized_pnl == 0.0
        assert pos.unrealized_pnl == 0.0

    def test_buy_adds_to_existing_position(self) -> None:
        """BUY: 加仓, 加权平均成本正确。"""
        existing = Position(
            instrument_id=1,
            quantity=500,
            available_quantity=500,
            average_cost=10.0,
            market_value=5000.0,
            unrealized_pnl=0.0,
            realized_pnl=0.0,
            total_fees=3.0,
        )
        account = _make_account(positions={1: existing})
        fill = _make_fill(filled_quantity=500, fill_price=12.0, fee=4.0)

        account.apply_fill(fill, settle_date="2026-03-02")

        pos = account.positions[1]
        assert pos.quantity == 1000
        # 加权平均: (10.0 * 500 + 12.0 * 500) / 1000 = 11.0
        assert pos.average_cost == pytest.approx(11.0)
        assert pos.market_value == pytest.approx(11.0 * 1000)
        # available_quantity 不变 — 新买入份额冻结
        assert pos.available_quantity == 500
        assert pos.total_fees == pytest.approx(7.0)

    def test_buy_debits_cash(self) -> None:
        """BUY: 现金减少 = amount + fee。"""
        account = _make_account(cash=100000.0)
        fill = _make_fill(filled_quantity=1000, fill_price=10.5, fee=5.0)

        account.apply_fill(fill, settle_date="2026-03-02")

        amount = 10.5 * 1000
        expected_available = 100000.0 - amount - 5.0
        expected_settled = 100000.0 - 5.0
        assert account.cash.available == pytest.approx(expected_available)
        assert account.cash.settled == pytest.approx(expected_settled)
        # frozen 不变
        assert account.cash.frozen == 0.0

    def test_buy_calls_frozen_callback(self) -> None:
        """BUY: on_frozen 回调被正确调用。"""
        account = _make_account()
        fill = _make_fill(filled_quantity=800, fill_price=10.0, fee=3.0)
        frozen_calls: list[tuple[int, str, int]] = []

        def on_frozen(instrument_id: int, settle_date: str, quantity: int) -> None:
            frozen_calls.append((instrument_id, settle_date, quantity))

        account.apply_fill(
            fill,
            settle_date="2026-03-03",
            on_frozen=on_frozen,
        )

        assert len(frozen_calls) == 1
        assert frozen_calls[0] == (1, "2026-03-03", 800)

    def test_buy_no_callback_does_not_error(self) -> None:
        """BUY: 不传 on_frozen 不报错 (T+0 场景)。"""
        account = _make_account()
        fill = _make_fill(filled_quantity=1000, fill_price=10.5, fee=5.0)

        account.apply_fill(fill, settle_date="2026-03-02")

        # Position created, available_quantity = 0 (no callback to thaw)
        pos = account.positions[1]
        assert pos.available_quantity == 0


class TestAccountApplyFillSell:
    """apply_fill SELL 场景。"""

    def test_sell_reduces_position(self) -> None:
        """SELL: 部分卖出, quantity 和 available_quantity 减少。"""
        existing = Position(
            instrument_id=1,
            quantity=1000,
            available_quantity=1000,
            average_cost=10.0,
            market_value=10000.0,
            unrealized_pnl=0.0,
            realized_pnl=0.0,
            total_fees=5.0,
        )
        account = _make_account(positions={1: existing})
        fill = _make_fill(
            direction=OrderSide.SELL,
            filled_quantity=400,
            fill_price=12.0,
            fee=3.0,
        )

        account.apply_fill(fill, settle_date="2026-03-02")

        pos = account.positions[1]
        assert pos.quantity == 600
        assert pos.available_quantity == 600
        # realized_pnl = (12.0 - 10.0) * 400 = 800
        assert pos.realized_pnl == pytest.approx(800.0)
        assert pos.market_value == pytest.approx(10.0 * 600)
        assert pos.total_fees == pytest.approx(8.0)

    def test_sell_complete_exit_removes_position(self) -> None:
        """SELL: 全部卖出, 仓位被移除。"""
        existing = Position(
            instrument_id=1,
            quantity=1000,
            available_quantity=1000,
            average_cost=10.0,
            market_value=10000.0,
            unrealized_pnl=0.0,
            realized_pnl=0.0,
            total_fees=5.0,
        )
        account = _make_account(positions={1: existing})
        fill = _make_fill(
            direction=OrderSide.SELL,
            filled_quantity=1000,
            fill_price=11.0,
            fee=3.0,
        )

        account.apply_fill(fill, settle_date="2026-03-02")

        assert 1 not in account.positions

    def test_sell_credits_cash(self) -> None:
        """SELL: 现金增加 = amount - fee。"""
        existing = Position(
            instrument_id=1,
            quantity=1000,
            available_quantity=1000,
            average_cost=10.0,
            market_value=10000.0,
            unrealized_pnl=0.0,
            realized_pnl=0.0,
            total_fees=5.0,
        )
        account = _make_account(cash=100000.0, positions={1: existing})
        fill = _make_fill(
            direction=OrderSide.SELL,
            filled_quantity=500,
            fill_price=12.0,
            fee=3.0,
        )

        account.apply_fill(fill, settle_date="2026-03-02")

        amount = 12.0 * 500
        expected_available = 100000.0 + amount - 3.0
        expected_settled = 100000.0 + amount - 3.0
        assert account.cash.available == pytest.approx(expected_available)
        assert account.cash.settled == pytest.approx(expected_settled)

    def test_sell_realized_pnl_calculation(self) -> None:
        """SELL: 已实现盈亏 = (卖出价 - 平均成本) * 数量。"""
        existing = Position(
            instrument_id=1,
            quantity=1000,
            available_quantity=1000,
            average_cost=10.0,
            market_value=10000.0,
            unrealized_pnl=0.0,
            realized_pnl=50.0,  # 之前有已实现盈亏
            total_fees=5.0,
        )
        account = _make_account(positions={1: existing})
        fill = _make_fill(
            direction=OrderSide.SELL,
            filled_quantity=300,
            fill_price=12.0,
            fee=3.0,
        )

        account.apply_fill(fill, settle_date="2026-03-02")

        pos = account.positions[1]
        # realized = 50.0 + (12.0 - 10.0) * 300 = 50.0 + 600.0
        assert pos.realized_pnl == pytest.approx(650.0)

    def test_sell_at_loss(self) -> None:
        """SELL: 亏损卖出, realized_pnl 为负。"""
        existing = Position(
            instrument_id=1,
            quantity=500,
            available_quantity=500,
            average_cost=10.0,
            market_value=5000.0,
            unrealized_pnl=0.0,
            realized_pnl=0.0,
            total_fees=2.0,
        )
        account = _make_account(positions={1: existing})
        fill = _make_fill(
            direction=OrderSide.SELL,
            filled_quantity=500,
            fill_price=8.0,
            fee=3.0,
        )

        account.apply_fill(fill, settle_date="2026-03-02")

        # 全部卖出, 仓位移除
        assert 1 not in account.positions
        # 但在移除前, realized_pnl = (8.0 - 10.0) * 500 = -1000
        # 验证通过 cash 变化间接确认
        amount = 8.0 * 500
        expected_available = 1000000.0 + amount - 3.0
        assert account.cash.available == pytest.approx(expected_available)

    def test_sell_does_not_call_frozen_callback(self) -> None:
        """SELL: on_frozen 回调不被调用。"""
        existing = Position(
            instrument_id=1,
            quantity=1000,
            available_quantity=1000,
            average_cost=10.0,
            market_value=10000.0,
            unrealized_pnl=0.0,
            realized_pnl=0.0,
            total_fees=5.0,
        )
        account = _make_account(positions={1: existing})
        fill = _make_fill(
            direction=OrderSide.SELL,
            filled_quantity=500,
            fill_price=12.0,
            fee=3.0,
        )
        frozen_calls: list[tuple[int, str, int]] = []

        def on_frozen(instrument_id: int, settle_date: str, quantity: int) -> None:
            frozen_calls.append((instrument_id, settle_date, quantity))

        account.apply_fill(
            fill,
            settle_date="2026-03-02",
            on_frozen=on_frozen,
        )

        assert len(frozen_calls) == 0


class TestAccountApplyFillEdgeCases:
    """apply_fill 边界场景。"""

    def test_buy_multiple_instruments(self) -> None:
        """多次买入不同标的, 各自独立。"""
        account = _make_account()
        fill1 = _make_fill(
            instrument_id=1,
            filled_quantity=500,
            fill_price=10.0,
            fee=3.0,
        )
        fill2 = _make_fill(
            fill_id="fill-2",
            order_id="ORD-002",
            instrument_id=2,
            filled_quantity=300,
            fill_price=20.0,
            fee=4.0,
        )

        account.apply_fill(fill1, settle_date="2026-03-02")
        account.apply_fill(fill2, settle_date="2026-03-02")

        assert len(account.positions) == 2
        assert account.positions[1].quantity == 500
        assert account.positions[2].quantity == 300

    def test_buy_sell_sequence(self) -> None:
        """买入后卖出完整序列。"""
        account = _make_account(cash=100000.0)
        buy_fill = _make_fill(filled_quantity=1000, fill_price=10.0, fee=5.0)
        sell_fill = _make_fill(
            fill_id="fill-2",
            order_id="ORD-002",
            direction=OrderSide.SELL,
            filled_quantity=1000,
            fill_price=11.0,
            fee=5.0,
        )

        account.apply_fill(buy_fill, settle_date="2026-03-02")
        # T+0: 模拟 Brokerage 立即解冻 (settle_date <= trade_date)
        pos = account.positions[1]
        account.positions[1] = Position(
            instrument_id=pos.instrument_id,
            quantity=pos.quantity,
            available_quantity=pos.quantity,  # 解冻
            average_cost=pos.average_cost,
            market_value=pos.market_value,
            unrealized_pnl=pos.unrealized_pnl,
            realized_pnl=pos.realized_pnl,
            total_fees=pos.total_fees,
        )

        account.apply_fill(sell_fill, settle_date="2026-03-02")

        assert 1 not in account.positions
        # Cash: 100000 - 10*1000 - 5 + 11*1000 - 5 = 100990
        assert account.cash.available == pytest.approx(100990.0)

    def test_sell_nonexistent_position_noop(self) -> None:
        """SELL: 仓位不存在时无操作 (Brokerage 应在调用前检查)。"""
        account = _make_account()
        fill = _make_fill(
            direction=OrderSide.SELL,
            filled_quantity=1000,
            fill_price=10.0,
            fee=5.0,
        )

        account.apply_fill(fill, settle_date="2026-03-02")

        assert 1 not in account.positions
        # Cash 仍应更新 (SELL credits cash)
        assert account.cash.available == pytest.approx(1_000_000.0 + 10000.0 - 5.0)

    def test_buy_zero_fee(self) -> None:
        """BUY: 零手续费场景。"""
        account = _make_account()
        fill = _make_fill(filled_quantity=1000, fill_price=10.0, fee=0.0)

        account.apply_fill(fill, settle_date="2026-03-02")

        pos = account.positions[1]
        assert pos.total_fees == 0.0
        assert account.cash.available == pytest.approx(1_000_000.0 - 10000.0)
        assert account.cash.settled == pytest.approx(1_000_000.0)
