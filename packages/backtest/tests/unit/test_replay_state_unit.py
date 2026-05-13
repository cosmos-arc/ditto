"""Tests for ReplayProof — fill and account state comparison."""

from __future__ import annotations

from datetime import datetime
from types import MappingProxyType

from ditto_backtest.replay import AccountStateComparison, FillComparison, ReplayProof
from ditto_kernel.identity import InstrumentId
from ditto_kernel.order import OrderSide
from ditto_portfolio.accounting import CashBook
from ditto_portfolio.accounting.account import AccountView
from ditto_portfolio.accounting.fills import FillEvent
from ditto_portfolio.accounting.position import Position

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_fill(
    instrument_id: InstrumentId = InstrumentId(600_000),
    direction: OrderSide = OrderSide.BUY,
    filled_quantity: int = 100,
    fill_price: float = 10.0,
    fee: float = 5.0,
    fill_id: str = "f1",
    order_id: str = "o1",
) -> FillEvent:
    return FillEvent(
        fill_id=fill_id,
        order_id=order_id,
        instrument_id=instrument_id,
        direction=direction,
        filled_quantity=filled_quantity,
        fill_price=fill_price,
        fee=fee,
        slippage=0.0,
        event_time=datetime(2024, 1, 15, 15, 0),
        cumulative_quantity=filled_quantity,
        leaves_quantity=0,
    )


def _account_view(
    nav: float = 100_000.0,
    cash: CashBook | None = None,
    positions: dict[InstrumentId, Position] | None = None,
) -> AccountView:
    return AccountView(
        positions=MappingProxyType(positions or {}),
        cash=cash or CashBook(available=nav, settled=nav, frozen=0.0),
        total_value=nav,
        nav=nav,
        exposure=0.0,
    )


# ---------------------------------------------------------------------------
# TestFillComparison
# ---------------------------------------------------------------------------


class TestFillComparison:
    """FillComparison frozen dataclass + ReplayProof.compare_fills."""

    def test_identical_fills(self) -> None:
        fills = [_make_fill(fill_id="f1"), _make_fill(fill_id="f2", fill_price=11.0)]
        result: FillComparison = ReplayProof.compare_fills(fills, fills)
        assert result.identical is True
        assert result.mismatch_count == 0
        assert result.length_mismatch is False

    def test_different_lengths(self) -> None:
        original = [
            _make_fill(fill_id="f1"),
            _make_fill(fill_id="f2"),
            _make_fill(fill_id="f3"),
        ]
        replay = [_make_fill(fill_id="f1"), _make_fill(fill_id="f2")]
        result = ReplayProof.compare_fills(original, replay)
        assert result.identical is False
        assert result.length_mismatch is True
        assert result.point_count == 3

    def test_different_prices(self) -> None:
        original = [_make_fill(fill_id="f1", fill_price=10.0)]
        replay = [_make_fill(fill_id="f1", fill_price=10.5)]
        result = ReplayProof.compare_fills(original, replay)
        assert result.identical is False
        assert result.mismatch_count > 0

    def test_empty_fills(self) -> None:
        result = ReplayProof.compare_fills([], [])
        assert result.identical is True
        assert result.mismatch_count == 0
        assert result.point_count == 0

    def test_different_fee_detected(self) -> None:
        """fee 不同但 fill_id/price/quantity 相同时，应判定为不一致。"""
        original = [_make_fill(fill_id="f1", fee=5.0)]
        replay = [_make_fill(fill_id="f1", fee=50.0)]
        result = ReplayProof.compare_fills(original, replay)
        assert result.identical is False
        assert result.mismatch_count > 0

    def test_different_instrument_detected(self) -> None:
        """instrument_id 不同但 fill_id/price/quantity 相同时，应判定为不一致。"""
        original = [_make_fill(instrument_id=InstrumentId(600_000))]
        replay = [_make_fill(instrument_id=InstrumentId(600_001))]
        result = ReplayProof.compare_fills(original, replay)
        assert result.identical is False


# ---------------------------------------------------------------------------
# TestAccountStateComparison
# ---------------------------------------------------------------------------


class TestAccountStateComparison:
    """AccountStateComparison frozen dataclass + ReplayProof.compare_account_state."""

    def test_identical_accounts(self) -> None:
        view = _account_view(nav=100_000.0)
        result: AccountStateComparison = ReplayProof.compare_account_state(view, view)
        assert result.identical is True
        assert result.nav_diff == 0.0
        assert result.cash_diff == 0.0
        assert result.position_count_diff == 0

    def test_different_nav(self) -> None:
        original = _account_view(nav=100_000.0)
        replay = _account_view(nav=99_500.0)
        result = ReplayProof.compare_account_state(original, replay)
        assert result.identical is False
        assert result.nav_diff == 500.0

    def test_different_cash(self) -> None:
        original = _account_view(
            nav=100_000.0,
            cash=CashBook(available=100_000.0, settled=100_000.0, frozen=0.0),
        )
        replay = _account_view(
            nav=100_000.0,
            cash=CashBook(available=90_000.0, settled=90_000.0, frozen=0.0),
        )
        result = ReplayProof.compare_account_state(original, replay)
        assert result.identical is False
        assert result.cash_diff == 10_000.0

    def test_different_positions(self) -> None:
        pos = Position(
            instrument_id=InstrumentId(600_000),
            quantity=100,
            available_quantity=100,
            average_cost=10.0,
            market_value=1000.0,
            unrealized_pnl=0.0,
            realized_pnl=0.0,
            total_fees=5.0,
        )
        original = _account_view(positions={InstrumentId(600_000): pos})
        replay = _account_view(positions={})
        result = ReplayProof.compare_account_state(original, replay)
        assert result.identical is False
        assert result.position_count_diff == 1

    def test_same_keys_different_quantity(self) -> None:
        """相同持仓 key 但 quantity 不同时，应判定为不一致。"""
        iid = InstrumentId(600_000)
        pos_a = Position(
            instrument_id=iid,
            quantity=100,
            available_quantity=100,
            average_cost=10.0,
            market_value=1000.0,
            unrealized_pnl=0.0,
            realized_pnl=0.0,
            total_fees=5.0,
        )
        pos_b = Position(
            instrument_id=iid,
            quantity=200,
            available_quantity=200,
            average_cost=10.0,
            market_value=2000.0,
            unrealized_pnl=0.0,
            realized_pnl=0.0,
            total_fees=5.0,
        )
        original = _account_view(
            nav=1000.0,
            positions={iid: pos_a},
        )
        replay = _account_view(
            nav=2000.0,
            positions={iid: pos_b},
        )
        result = ReplayProof.compare_account_state(original, replay)
        assert result.identical is False
