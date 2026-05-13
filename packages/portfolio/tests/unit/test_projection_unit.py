"""Tests for portfolio state projection — AccountProjector / FillProjector."""

from __future__ import annotations

from datetime import datetime

import pytest
from ditto_kernel.identity import InstrumentId
from ditto_kernel.order import OrderSide
from ditto_portfolio.accounting.account import Account
from ditto_portfolio.accounting.cash import CashBook
from ditto_portfolio.accounting.fills import FillEvent
from ditto_portfolio.projection import AccountProjector, PortfolioStateSnapshot

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_INSTRUMENT: InstrumentId = InstrumentId(600000)


def _make_fill(
    instrument_id: InstrumentId = InstrumentId(600_000),
    direction: OrderSide = OrderSide.BUY,
    filled_quantity: int = 100,
    fill_price: float = 10.0,
    fee: float = 5.0,
    slippage: float = 0.0,
    fill_id: str = "f1",
    order_id: str = "o1",
    event_time: datetime = datetime(2024, 1, 15, 15, 0),
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
        event_time=event_time,
        cumulative_quantity=filled_quantity,
        leaves_quantity=0,
    )


# ---------------------------------------------------------------------------
# TestAccountProjector
# ---------------------------------------------------------------------------


class TestAccountProjectorEmptyFills:
    """空 fill 流场景。"""

    def test_empty_fills_produces_empty_snapshot(self) -> None:
        """AccountProjector 无成交 → 空 positions + 零 CashBook。"""
        projector = AccountProjector(
            initial_cash=CashBook(available=0.0, settled=0.0, frozen=0.0),
        )
        snapshot = projector.project([])

        assert isinstance(snapshot, PortfolioStateSnapshot)
        assert snapshot.positions == {}
        assert snapshot.cash.available == 0.0
        assert snapshot.cash.settled == 0.0
        assert snapshot.cash.frozen == 0.0


class TestAccountProjectorBuyFill:
    """BUY fill 投影场景。"""

    def test_single_buy_fill_produces_position(self) -> None:
        """单次 BUY → 产生正确 quantity / average_cost 的 Position。"""
        projector = AccountProjector(
            initial_cash=CashBook(available=100_000.0, settled=100_000.0, frozen=0.0),
        )
        fill = _make_fill(filled_quantity=100, fill_price=10.0, fee=5.0)
        snapshot = projector.project([fill])

        assert _INSTRUMENT in snapshot.positions
        pos = snapshot.positions[_INSTRUMENT]
        assert pos.quantity == 100
        assert pos.average_cost == pytest.approx(10.0)
        assert pos.total_fees == pytest.approx(5.0)

    def test_cash_decreases_on_buy(self) -> None:
        """BUY fill → cash.available 减少 price * qty + fee。"""
        projector = AccountProjector(
            initial_cash=CashBook(available=100_000.0, settled=100_000.0, frozen=0.0),
        )
        fill = _make_fill(filled_quantity=100, fill_price=10.0, fee=5.0)
        snapshot = projector.project([fill])

        expected_available = 100_000.0 - 10.0 * 100 - 5.0
        assert snapshot.cash.available == pytest.approx(expected_available)
        assert snapshot.cash.frozen == 0.0


class TestAccountProjectorSellFill:
    """SELL fill 投影场景。"""

    def test_sell_fill_reduces_position(self) -> None:
        """BUY 后 SELL → 持仓减少或清空。"""
        projector = AccountProjector(
            initial_cash=CashBook(available=100_000.0, settled=100_000.0, frozen=0.0),
        )
        buy_fill = _make_fill(filled_quantity=100, fill_price=10.0, fee=5.0)
        # 卖出一半
        sell_fill = _make_fill(
            fill_id="f2",
            order_id="o2",
            direction=OrderSide.SELL,
            filled_quantity=50,
            fill_price=12.0,
            fee=3.0,
        )

        # AccountProjector 使用 Account 内部累加，需要先让 BUY 的持仓
        # available_quantity 可卖（模拟 T+0 解冻）无法通过 projector 接口操作，
        # 所以直接验证 SELL 后持仓数量减少
        snapshot = projector.project([buy_fill, sell_fill])

        pos = snapshot.positions[_INSTRUMENT]
        assert pos.quantity == 50
        # realized_pnl = (12.0 - 10.0) * 50 = 100
        assert pos.realized_pnl == pytest.approx(100.0)

    def test_sell_fill_removes_position_on_full_exit(self) -> None:
        """BUY 后全部 SELL → 持仓被完全移除。"""
        projector = AccountProjector(
            initial_cash=CashBook(available=100_000.0, settled=100_000.0, frozen=0.0),
        )
        buy_fill = _make_fill(filled_quantity=100, fill_price=10.0, fee=5.0)
        sell_fill = _make_fill(
            fill_id="f2",
            order_id="o2",
            direction=OrderSide.SELL,
            filled_quantity=100,
            fill_price=12.0,
            fee=3.0,
        )
        snapshot = projector.project([buy_fill, sell_fill])

        assert _INSTRUMENT not in snapshot.positions

    def test_cash_increases_on_sell(self) -> None:
        """SELL fill → cash.available 增加 price * qty - fee。"""
        projector = AccountProjector(
            initial_cash=CashBook(available=100_000.0, settled=100_000.0, frozen=0.0),
        )
        buy_fill = _make_fill(filled_quantity=100, fill_price=10.0, fee=5.0)
        sell_fill = _make_fill(
            fill_id="f2",
            order_id="o2",
            direction=OrderSide.SELL,
            filled_quantity=100,
            fill_price=12.0,
            fee=3.0,
        )
        snapshot = projector.project([buy_fill, sell_fill])

        # BUY: 100_000 - 10*100 - 5 = 98_995
        # SELL: 98_995 + 12*100 - 3 = 100_192
        expected_available = 100_000.0 - 10.0 * 100 - 5.0 + 12.0 * 100 - 3.0
        assert snapshot.cash.available == pytest.approx(expected_available)


class TestAccountProjectorParity:
    """AccountProjector 与 Account.apply_fill 一致性验证。"""

    def test_projection_matches_account_apply_fill(self) -> None:
        """AccountProjector.project(fills) 与手动 Account.apply_fill 结果一致。"""
        initial_cash = CashBook(available=100_000.0, settled=100_000.0, frozen=0.0)
        fills = [
            _make_fill(
                fill_id="f1",
                order_id="o1",
                filled_quantity=200,
                fill_price=10.0,
                fee=5.0,
            ),
            _make_fill(
                fill_id="f2",
                order_id="o2",
                instrument_id=InstrumentId(600_001),
                filled_quantity=300,
                fill_price=8.0,
                fee=4.0,
            ),
            _make_fill(
                fill_id="f3",
                order_id="o3",
                direction=OrderSide.SELL,
                filled_quantity=100,
                fill_price=11.0,
                fee=3.0,
            ),
        ]

        # 路径 A: AccountProjector
        projector = AccountProjector(initial_cash=initial_cash)
        snapshot = projector.project(fills)

        # 路径 B: 手动 Account.apply_fill
        account = Account(cash=initial_cash)
        for fill in fills:
            account.apply_fill(fill, settle_date="1970-01-01")

        # 验证 positions 一致
        assert set(snapshot.positions.keys()) == set(account.positions.keys())
        for iid in snapshot.positions:
            snap_pos = snapshot.positions[iid]
            acct_pos = dict(account.positions)[iid]
            assert snap_pos.quantity == acct_pos.quantity
            assert snap_pos.average_cost == pytest.approx(acct_pos.average_cost)
            assert snap_pos.market_value == pytest.approx(acct_pos.market_value)
            assert snap_pos.total_fees == pytest.approx(acct_pos.total_fees)

        # 验证 cash 一致
        assert snapshot.cash.available == pytest.approx(account.cash.available)
        assert snapshot.cash.settled == pytest.approx(account.cash.settled)
        assert snapshot.cash.frozen == pytest.approx(account.cash.frozen)


class TestAccountProjectorIdempotency:
    """project() 多次调用不应累积状态。"""

    def test_repeated_project_resets_state(self) -> None:
        """同一 projector 调用 project() 两次，第二次结果应独立于第一次。"""
        initial_cash = CashBook(available=100_000.0, settled=100_000.0, frozen=0.0)
        projector = AccountProjector(initial_cash=initial_cash)

        buy_fill = _make_fill(filled_quantity=100, fill_price=10.0, fee=5.0)
        projector.project([buy_fill])

        # 第二次调用 — 同样的 fill，应产生相同结果
        snapshot2 = projector.project([buy_fill])
        pos = snapshot2.positions[_INSTRUMENT]
        assert pos.quantity == 100
        assert pos.total_fees == pytest.approx(5.0)

    def test_repeated_project_empty_resets_to_initial(self) -> None:
        """先 project 有 fill，再 project 空 → 应回到初始状态。"""
        initial_cash = CashBook(available=100_000.0, settled=100_000.0, frozen=0.0)
        projector = AccountProjector(initial_cash=initial_cash)

        buy_fill = _make_fill(filled_quantity=100, fill_price=10.0, fee=5.0)
        projector.project([buy_fill])

        snapshot2 = projector.project([])
        assert snapshot2.positions == {}
        assert snapshot2.cash == initial_cash
