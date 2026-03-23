"""FifoTradeBuilder unit tests."""

from datetime import datetime
from types import MappingProxyType

import pytest
from ditto_core.accounting.account import AccountView
from ditto_core.accounting.cash import CashBook
from ditto_core.accounting.order_book import OrderBookReadOnly, OrderDirection
from ditto_core.execution.fills import FillEvent
from ditto_core.execution.trade_builder import (
    FifoTradeBuilder,
    TradeMatchingMethod,
    TradeRecord,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def account_view() -> AccountView:
    """Minimal account view for testing."""
    return AccountView(
        positions=MappingProxyType({}),
        cash=CashBook(available=1_000_000.0, settled=1_000_000.0, frozen=0.0),
        total_value=1_000_000.0,
        nav=1_000_000.0,
        exposure=0.0,
        pending_buy_value=0.0,
        order_book=OrderBookReadOnly({}),
    )


def _fill(
    fill_id: str,
    order_id: str = "order-1",
    instrument_id: str = "ETF-001",
    direction: OrderDirection = OrderDirection.BUY,
    quantity: int = 100,
    price: float = 10.0,
    fee: float = 5.0,
    event_time: datetime | None = None,
) -> FillEvent:
    """Create a FillEvent for testing."""
    return FillEvent(
        fill_id=fill_id,
        order_id=order_id,
        instrument_id=instrument_id,
        direction=direction,
        filled_quantity=quantity,
        fill_price=price,
        fee=fee,
        slippage=0.0,
        event_time=event_time or datetime(2026, 3, 1, 9, 30),
        cumulative_quantity=quantity,
        leaves_quantity=0,
    )


# ---------------------------------------------------------------------------
# TradeRecord
# ---------------------------------------------------------------------------


class TestTradeRecord:
    def test_frozen(self) -> None:
        record = TradeRecord(
            trade_id="t-1",
            instrument_id="ETF-001",
            direction=OrderDirection.BUY,
            entry_date="2026-03-01",
            exit_date=None,
            entry_price=10.0,
            exit_price=None,
            quantity=100,
            gross_pnl=None,
            fees=5.0,
            net_pnl=None,
            holding_days=None,
            return_pct=None,
            entry_order_ids=("o-1",),
            exit_order_ids=(),
        )
        with pytest.raises(AttributeError):
            record.trade_id = "t-2"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# TradeMatchingMethod
# ---------------------------------------------------------------------------


class TestTradeMatchingMethod:
    def test_fifo_value(self) -> None:
        assert TradeMatchingMethod.FIFO == "fifo"

    def test_flat_to_flat_value(self) -> None:
        assert TradeMatchingMethod.FLAT_TO_FLAT == "flat_to_flat"


# ---------------------------------------------------------------------------
# FifoTradeBuilder — basic
# ---------------------------------------------------------------------------


class TestFifoBasic:
    def test_single_buy_creates_open_trade(self, account_view: AccountView) -> None:
        builder = FifoTradeBuilder()
        builder.on_fill(_fill("f-1", order_id="o-buy"), account_view)

        open_trades = builder.get_open_trades()
        assert len(open_trades) == 1
        assert open_trades[0].instrument_id == "ETF-001"
        assert open_trades[0].quantity == 100
        assert open_trades[0].entry_price == 10.0
        assert open_trades[0].direction == OrderDirection.BUY
        assert open_trades[0].exit_date is None

    def test_buy_then_sell_creates_closed_trade(
        self, account_view: AccountView
    ) -> None:
        builder = FifoTradeBuilder()
        buy = _fill("f-1", order_id="o-buy", quantity=100, price=10.0)
        sell = _fill(
            "f-2",
            order_id="o-sell",
            direction=OrderDirection.SELL,
            quantity=100,
            price=11.0,
            event_time=datetime(2026, 3, 5),
        )

        builder.on_fill(buy, account_view)
        builder.on_fill(sell, account_view)

        closed = builder.get_closed_trades()
        assert len(closed) == 1
        assert closed[0].exit_price == 11.0
        assert closed[0].quantity == 100
        assert closed[0].gross_pnl == pytest.approx(100.0)
        assert closed[0].fees == pytest.approx(10.0)
        assert closed[0].net_pnl == pytest.approx(90.0)
        assert closed[0].exit_date == "2026-03-05"
        assert closed[0].holding_days == 4
        assert closed[0].return_pct == pytest.approx(10.0)

        assert builder.get_open_trades() == ()


# ---------------------------------------------------------------------------
# FifoTradeBuilder — multi entry FIFO
# ---------------------------------------------------------------------------


class TestFifoMultiEntry:
    def test_fifo_closes_earliest_first(self, account_view: AccountView) -> None:
        """Multiple buys + one sell → FIFO closes the earliest open trade."""
        builder = FifoTradeBuilder()

        buy1 = _fill(
            "f-1",
            order_id="o-1",
            quantity=100,
            price=10.0,
            event_time=datetime(2026, 3, 1),
        )
        buy2 = _fill(
            "f-2",
            order_id="o-2",
            quantity=200,
            price=11.0,
            event_time=datetime(2026, 3, 2),
        )
        sell = _fill(
            "f-3",
            order_id="o-3",
            direction=OrderDirection.SELL,
            quantity=100,
            price=12.0,
            event_time=datetime(2026, 3, 5),
        )

        builder.on_fill(buy1, account_view)
        builder.on_fill(buy2, account_view)
        builder.on_fill(sell, account_view)

        closed = builder.get_closed_trades()
        assert len(closed) == 1
        assert closed[0].entry_price == pytest.approx(10.0)
        assert closed[0].exit_price == pytest.approx(12.0)
        assert closed[0].gross_pnl == pytest.approx(200.0)

        open_trades = builder.get_open_trades()
        assert len(open_trades) == 1
        assert open_trades[0].quantity == 200
        assert open_trades[0].entry_price == pytest.approx(11.0)


# ---------------------------------------------------------------------------
# FifoTradeBuilder — partial close
# ---------------------------------------------------------------------------


class TestFifoPartialClose:
    def test_partial_close_splits_trade(self, account_view: AccountView) -> None:
        """Sell 50 of 100 → partial close, 50 remains open."""
        builder = FifoTradeBuilder()

        buy = _fill("f-1", order_id="o-1", quantity=100, price=10.0)
        sell = _fill(
            "f-2",
            order_id="o-2",
            direction=OrderDirection.SELL,
            quantity=50,
            price=11.0,
            event_time=datetime(2026, 3, 3),
        )

        builder.on_fill(buy, account_view)
        builder.on_fill(sell, account_view)

        closed = builder.get_closed_trades()
        assert len(closed) == 1
        assert closed[0].quantity == 50
        assert closed[0].gross_pnl == pytest.approx(50.0)
        # buy fee share: 5.0 * 50/100 = 2.5; sell fee share: 5.0 * 50/50 = 5.0
        assert closed[0].fees == pytest.approx(7.5)
        assert closed[0].net_pnl == pytest.approx(42.5)

        open_trades = builder.get_open_trades()
        assert len(open_trades) == 1
        assert open_trades[0].quantity == 50

    def test_sell_spanning_two_entries(self, account_view: AccountView) -> None:
        """Sell 150 spanning two entries (100 + 100) → 2 closed + 1 open."""
        builder = FifoTradeBuilder()

        buy1 = _fill("f-1", order_id="o-1", quantity=100, price=10.0, fee=5.0)
        buy2 = _fill("f-2", order_id="o-2", quantity=100, price=12.0, fee=5.0)
        sell = _fill(
            "f-3",
            order_id="o-3",
            direction=OrderDirection.SELL,
            quantity=150,
            price=13.0,
            fee=6.0,
            event_time=datetime(2026, 3, 5),
        )

        builder.on_fill(buy1, account_view)
        builder.on_fill(buy2, account_view)
        builder.on_fill(sell, account_view)

        closed = builder.get_closed_trades()
        assert len(closed) == 2
        # First closed: 100 from buy1
        assert closed[0].quantity == 100
        assert closed[0].entry_price == pytest.approx(10.0)
        assert closed[0].exit_price == pytest.approx(13.0)
        assert closed[0].gross_pnl == pytest.approx(300.0)
        # buy fee: 5.0 * 100/100 = 5.0; sell fee: 6.0 * 100/150 = 4.0
        assert closed[0].fees == pytest.approx(9.0)
        # Second closed: 50 from buy2
        assert closed[1].quantity == 50
        assert closed[1].entry_price == pytest.approx(12.0)
        assert closed[1].gross_pnl == pytest.approx(50.0)
        # buy fee: 5.0 * 50/100 = 2.5; sell fee: 6.0 * 50/150 = 2.0
        assert closed[1].fees == pytest.approx(4.5)

        open_trades = builder.get_open_trades()
        assert len(open_trades) == 1
        assert open_trades[0].quantity == 50  # Remaining from second entry


# ---------------------------------------------------------------------------
# FifoTradeBuilder — flush
# ---------------------------------------------------------------------------


class TestFifoFlush:
    def test_flush_returns_open_trades(self, account_view: AccountView) -> None:
        """flush() returns all open trades and clears internal state."""
        builder = FifoTradeBuilder()

        builder.on_fill(
            _fill("f-1", order_id="o-1", quantity=100, price=10.0), account_view
        )

        flushed = builder.flush()
        assert len(flushed) == 1
        assert flushed[0].exit_date is None

        assert builder.get_open_trades() == ()

    def test_flush_preserves_closed_trades(self, account_view: AccountView) -> None:
        """flush() does not affect closed trades."""
        builder = FifoTradeBuilder()
        buy = _fill("f-1", order_id="o-1", quantity=100, price=10.0)
        sell = _fill(
            "f-2",
            order_id="o-2",
            direction=OrderDirection.SELL,
            quantity=100,
            price=11.0,
            event_time=datetime(2026, 3, 5),
        )

        builder.on_fill(buy, account_view)
        builder.on_fill(sell, account_view)

        builder.flush()

        closed = builder.get_closed_trades()
        assert len(closed) == 1


# ---------------------------------------------------------------------------
# FifoTradeBuilder — excess sell
# ---------------------------------------------------------------------------


class TestFifoExcessSell:
    def test_sell_exceeding_open_ignores_excess(
        self, account_view: AccountView
    ) -> None:
        """Sell more than open position → close all, ignore excess."""
        builder = FifoTradeBuilder()

        buy = _fill("f-1", order_id="o-1", quantity=100, price=10.0, fee=5.0)
        sell = _fill(
            "f-2",
            order_id="o-2",
            direction=OrderDirection.SELL,
            quantity=200,
            price=12.0,
            fee=5.0,
            event_time=datetime(2026, 3, 5),
        )

        builder.on_fill(buy, account_view)
        builder.on_fill(sell, account_view)

        closed = builder.get_closed_trades()
        assert len(closed) == 1
        assert closed[0].quantity == 100
        assert closed[0].gross_pnl == pytest.approx(200.0)
        # buy fee: 5.0 * 100/100 = 5.0; sell fee: 5.0 * 100/200 = 2.5
        assert closed[0].fees == pytest.approx(7.5)

        assert builder.get_open_trades() == ()


# ---------------------------------------------------------------------------
# FifoTradeBuilder — multi-instrument
# ---------------------------------------------------------------------------


class TestFifoMultiInstrument:
    def test_sell_matches_same_instrument(self, account_view: AccountView) -> None:
        """Sell instrument A only matches buys of instrument A."""
        builder = FifoTradeBuilder()

        buy_a = _fill(
            "f-1", order_id="o-1", instrument_id="ETF-A", quantity=100, price=10.0
        )
        buy_b = _fill(
            "f-2", order_id="o-2", instrument_id="ETF-B", quantity=200, price=20.0
        )
        sell_a = _fill(
            "f-3",
            order_id="o-3",
            instrument_id="ETF-A",
            direction=OrderDirection.SELL,
            quantity=100,
            price=11.0,
            event_time=datetime(2026, 3, 5),
        )

        builder.on_fill(buy_a, account_view)
        builder.on_fill(buy_b, account_view)
        builder.on_fill(sell_a, account_view)

        closed = builder.get_closed_trades()
        assert len(closed) == 1
        assert closed[0].instrument_id == "ETF-A"

        open_trades = builder.get_open_trades()
        assert len(open_trades) == 1
        assert open_trades[0].instrument_id == "ETF-B"

    def test_sell_with_no_open_is_ignored(self, account_view: AccountView) -> None:
        """Sell for instrument with no open positions is a no-op."""
        builder = FifoTradeBuilder()

        sell = _fill(
            "f-1",
            order_id="o-1",
            direction=OrderDirection.SELL,
            quantity=100,
            price=11.0,
        )
        builder.on_fill(sell, account_view)

        assert builder.get_closed_trades() == ()
        assert builder.get_open_trades() == ()
