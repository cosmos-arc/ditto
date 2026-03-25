"""FifoTradeBuilder + FlatToFlatTradeBuilder unit tests."""

from datetime import datetime
from types import MappingProxyType

import pytest
from ditto_core.accounting.account import AccountView
from ditto_core.accounting.cash import CashBook
from ditto_core.accounting.fills import FillEvent
from ditto_core.accounting.order_book import OrderBookReadOnly
from ditto_core.execution.trade_builder import (
    FifoTradeBuilder,
    FlatToFlatTradeBuilder,
    TradeMatchingMethod,
    TradeRecord,
)
from ditto_kernel.enums import OrderSide

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
    instrument_id: int = 1,
    direction: OrderSide = OrderSide.BUY,
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
            instrument_id=1,
            direction=OrderSide.BUY,
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
        assert open_trades[0].instrument_id == 1
        assert open_trades[0].quantity == 100
        assert open_trades[0].entry_price == 10.0
        assert open_trades[0].direction == OrderSide.BUY
        assert open_trades[0].exit_date is None

    def test_buy_then_sell_creates_closed_trade(
        self, account_view: AccountView
    ) -> None:
        builder = FifoTradeBuilder()
        buy = _fill("f-1", order_id="o-buy", quantity=100, price=10.0)
        sell = _fill(
            "f-2",
            order_id="o-sell",
            direction=OrderSide.SELL,
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
            direction=OrderSide.SELL,
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
            direction=OrderSide.SELL,
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
            direction=OrderSide.SELL,
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
            direction=OrderSide.SELL,
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
            direction=OrderSide.SELL,
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

        buy_a = _fill("f-1", order_id="o-1", instrument_id=2, quantity=100, price=10.0)
        buy_b = _fill("f-2", order_id="o-2", instrument_id=3, quantity=200, price=20.0)
        sell_a = _fill(
            "f-3",
            order_id="o-3",
            instrument_id=2,
            direction=OrderSide.SELL,
            quantity=100,
            price=11.0,
            event_time=datetime(2026, 3, 5),
        )

        builder.on_fill(buy_a, account_view)
        builder.on_fill(buy_b, account_view)
        builder.on_fill(sell_a, account_view)

        closed = builder.get_closed_trades()
        assert len(closed) == 1
        assert closed[0].instrument_id == 2

        open_trades = builder.get_open_trades()
        assert len(open_trades) == 1
        assert open_trades[0].instrument_id == 3

    def test_sell_with_no_open_is_ignored(self, account_view: AccountView) -> None:
        """Sell for instrument with no open positions is a no-op."""
        builder = FifoTradeBuilder()

        sell = _fill(
            "f-1",
            order_id="o-1",
            direction=OrderSide.SELL,
            quantity=100,
            price=11.0,
        )
        builder.on_fill(sell, account_view)

        assert builder.get_closed_trades() == ()
        assert builder.get_open_trades() == ()


# ---------------------------------------------------------------------------
# FlatToFlatTradeBuilder — basic: single buy → single sell
# ---------------------------------------------------------------------------


class TestFlatToFlatBasic:
    def test_single_buy_creates_open_trade(self, account_view: AccountView) -> None:
        """Single BUY → one open trade, no closed trades."""
        builder = FlatToFlatTradeBuilder()
        builder.on_fill(_fill("f-1", order_id="o-buy"), account_view)

        open_trades = builder.get_open_trades()
        assert len(open_trades) == 1
        assert open_trades[0].instrument_id == 1
        assert open_trades[0].quantity == 100
        assert open_trades[0].entry_price == pytest.approx(10.0)
        assert open_trades[0].direction == OrderSide.BUY
        assert open_trades[0].exit_date is None
        assert open_trades[0].exit_price is None

        assert builder.get_closed_trades() == ()

    def test_buy_then_sell_creates_closed_trade(
        self, account_view: AccountView
    ) -> None:
        """Buy 100 @10, sell 100 @11 → net=0, one closed trade."""
        builder = FlatToFlatTradeBuilder()

        buy = _fill("f-1", order_id="o-buy", quantity=100, price=10.0, fee=5.0)
        sell = _fill(
            "f-2",
            order_id="o-sell",
            direction=OrderSide.SELL,
            quantity=100,
            price=11.0,
            fee=5.0,
            event_time=datetime(2026, 3, 5),
        )

        builder.on_fill(buy, account_view)
        builder.on_fill(sell, account_view)

        closed = builder.get_closed_trades()
        assert len(closed) == 1
        assert closed[0].entry_price == pytest.approx(10.0)
        assert closed[0].exit_price == pytest.approx(11.0)
        assert closed[0].quantity == 100
        assert closed[0].gross_pnl == pytest.approx(100.0)
        assert closed[0].fees == pytest.approx(10.0)
        assert closed[0].net_pnl == pytest.approx(90.0)
        assert closed[0].holding_days == 4
        assert closed[0].return_pct == pytest.approx(10.0)
        assert closed[0].exit_date == "2026-03-05"
        assert closed[0].entry_order_ids == ("o-buy",)
        assert closed[0].exit_order_ids == ("o-sell",)

        assert builder.get_open_trades() == ()


# ---------------------------------------------------------------------------
# FlatToFlatTradeBuilder — multiple buys → single sell (VWAP entry)
# ---------------------------------------------------------------------------


class TestFlatToFlatMultiBuy:
    def test_multiple_buys_vwap_entry(self, account_view: AccountView) -> None:
        """Buy 100 @10 + buy 100 @14 → VWAP entry 12.0, sell 200 @15."""
        builder = FlatToFlatTradeBuilder()

        buy1 = _fill(
            "f-1",
            order_id="o-b1",
            quantity=100,
            price=10.0,
            fee=5.0,
            event_time=datetime(2026, 3, 1),
        )
        buy2 = _fill(
            "f-2",
            order_id="o-b2",
            quantity=100,
            price=14.0,
            fee=7.0,
            event_time=datetime(2026, 3, 2),
        )
        sell = _fill(
            "f-3",
            order_id="o-s1",
            direction=OrderSide.SELL,
            quantity=200,
            price=15.0,
            fee=8.0,
            event_time=datetime(2026, 3, 10),
        )

        builder.on_fill(buy1, account_view)
        builder.on_fill(buy2, account_view)
        builder.on_fill(sell, account_view)

        # net = 100+100-200 = 0 → closed
        assert len(builder.get_open_trades()) == 0

        closed = builder.get_closed_trades()
        assert len(closed) == 1
        # VWAP entry: (100*10 + 100*14) / 200 = 12.0
        assert closed[0].entry_price == pytest.approx(12.0)
        assert closed[0].exit_price == pytest.approx(15.0)
        assert closed[0].quantity == 200
        # gross: 200*15 - 200*12 = 600
        assert closed[0].gross_pnl == pytest.approx(600.0)
        assert closed[0].fees == pytest.approx(5.0 + 7.0 + 8.0)
        assert closed[0].net_pnl == pytest.approx(600.0 - 20.0)
        # holding: 2026-03-10 - 2026-03-01 = 9 days
        assert closed[0].holding_days == 9
        # return: 600 / 2400 * 100 = 25%
        assert closed[0].return_pct == pytest.approx(25.0)
        assert closed[0].entry_order_ids == ("o-b1", "o-b2")
        assert closed[0].exit_order_ids == ("o-s1",)


# ---------------------------------------------------------------------------
# FlatToFlatTradeBuilder — single buy → multiple sells (VWAP exit)
# ---------------------------------------------------------------------------


class TestFlatToFlatMultiSell:
    def test_single_buy_multiple_sells_vwap_exit(
        self, account_view: AccountView
    ) -> None:
        """Buy 300 @10, sell 100 @11 + sell 200 @14 → VWAP exit 13.0."""
        builder = FlatToFlatTradeBuilder()

        buy = _fill(
            "f-1",
            order_id="o-b1",
            quantity=300,
            price=10.0,
            fee=15.0,
            event_time=datetime(2026, 3, 1),
        )
        sell1 = _fill(
            "f-2",
            order_id="o-s1",
            direction=OrderSide.SELL,
            quantity=100,
            price=11.0,
            fee=4.0,
            event_time=datetime(2026, 3, 5),
        )
        sell2 = _fill(
            "f-3",
            order_id="o-s2",
            direction=OrderSide.SELL,
            quantity=200,
            price=14.0,
            fee=6.0,
            event_time=datetime(2026, 3, 8),
        )

        builder.on_fill(buy, account_view)
        builder.on_fill(sell1, account_view)
        builder.on_fill(sell2, account_view)

        # net = 300-100-200 = 0 → closed
        assert len(builder.get_open_trades()) == 0

        closed = builder.get_closed_trades()
        assert len(closed) == 1
        assert closed[0].entry_price == pytest.approx(10.0)
        # VWAP exit: (100*11 + 200*14) / 300 = 3900/300 = 13.0
        assert closed[0].exit_price == pytest.approx(13.0)
        assert closed[0].quantity == 300
        # gross: 3900 - 3000 = 900
        assert closed[0].gross_pnl == pytest.approx(900.0)
        assert closed[0].fees == pytest.approx(15.0 + 4.0 + 6.0)
        # holding: 2026-03-08 - 2026-03-01 = 7 days
        assert closed[0].holding_days == 7
        assert closed[0].entry_order_ids == ("o-b1",)
        assert closed[0].exit_order_ids == ("o-s1", "o-s2")


# ---------------------------------------------------------------------------
# FlatToFlatTradeBuilder — partial position (net != 0)
# ---------------------------------------------------------------------------


class TestFlatToFlatPartial:
    def test_partial_sell_no_closed_trade(self, account_view: AccountView) -> None:
        """Buy 200, sell 100 → net=100, no closed trade, 100 open."""
        builder = FlatToFlatTradeBuilder()

        buy = _fill("f-1", order_id="o-b1", quantity=200, price=10.0, fee=10.0)
        sell = _fill(
            "f-2",
            order_id="o-s1",
            direction=OrderSide.SELL,
            quantity=100,
            price=11.0,
            fee=5.0,
            event_time=datetime(2026, 3, 5),
        )

        builder.on_fill(buy, account_view)
        builder.on_fill(sell, account_view)

        assert builder.get_closed_trades() == ()

        open_trades = builder.get_open_trades()
        assert len(open_trades) == 1
        assert open_trades[0].quantity == 100
        # VWAP entry remains at 10.0 (only one buy)
        assert open_trades[0].entry_price == pytest.approx(10.0)

    def test_partial_then_full_close(self, account_view: AccountView) -> None:
        """Buy 200, sell 100 (partial), sell 100 (close) → one closed trade."""
        builder = FlatToFlatTradeBuilder()

        buy = _fill(
            "f-1",
            order_id="o-b1",
            quantity=200,
            price=10.0,
            fee=10.0,
            event_time=datetime(2026, 3, 1),
        )
        sell1 = _fill(
            "f-2",
            order_id="o-s1",
            direction=OrderSide.SELL,
            quantity=100,
            price=11.0,
            fee=5.0,
            event_time=datetime(2026, 3, 5),
        )
        sell2 = _fill(
            "f-3",
            order_id="o-s2",
            direction=OrderSide.SELL,
            quantity=100,
            price=12.0,
            fee=5.0,
            event_time=datetime(2026, 3, 8),
        )

        builder.on_fill(buy, account_view)
        builder.on_fill(sell1, account_view)

        # Partial: no closed
        assert builder.get_closed_trades() == ()
        assert len(builder.get_open_trades()) == 1

        builder.on_fill(sell2, account_view)

        # Now net = 200-100-100 = 0 → closed
        closed = builder.get_closed_trades()
        assert len(closed) == 1
        assert closed[0].entry_price == pytest.approx(10.0)
        # VWAP exit: (100*11 + 100*12) / 200 = 11.5
        assert closed[0].exit_price == pytest.approx(11.5)
        assert closed[0].quantity == 200
        # gross: 2300 - 2000 = 300
        assert closed[0].gross_pnl == pytest.approx(300.0)
        assert closed[0].fees == pytest.approx(10.0 + 5.0 + 5.0)
        # holding: 2026-03-08 - 2026-03-01 = 7 days
        assert closed[0].holding_days == 7
        assert builder.get_open_trades() == ()


# ---------------------------------------------------------------------------
# FlatToFlatTradeBuilder — flush
# ---------------------------------------------------------------------------


class TestFlatToFlatFlush:
    def test_flush_returns_remaining_open(self, account_view: AccountView) -> None:
        """flush() returns open position as open trade and clears state."""
        builder = FlatToFlatTradeBuilder()

        builder.on_fill(
            _fill("f-1", order_id="o-b1", quantity=100, price=10.0, fee=5.0),
            account_view,
        )

        flushed = builder.flush()
        assert len(flushed) == 1
        assert flushed[0].exit_date is None
        assert flushed[0].exit_price is None
        assert flushed[0].quantity == 100

        assert builder.get_open_trades() == ()

    def test_flush_after_partial_sell(self, account_view: AccountView) -> None:
        """Buy 200, sell 100, flush → returns 100 remaining as open."""
        builder = FlatToFlatTradeBuilder()

        buy = _fill(
            "f-1",
            order_id="o-b1",
            quantity=200,
            price=10.0,
            fee=10.0,
            event_time=datetime(2026, 3, 1),
        )
        sell = _fill(
            "f-2",
            order_id="o-s1",
            direction=OrderSide.SELL,
            quantity=100,
            price=11.0,
            fee=5.0,
            event_time=datetime(2026, 3, 5),
        )

        builder.on_fill(buy, account_view)
        builder.on_fill(sell, account_view)

        flushed = builder.flush()
        assert len(flushed) == 1
        assert flushed[0].quantity == 100
        assert flushed[0].exit_date is None

        assert builder.get_open_trades() == ()

    def test_flush_preserves_closed_trades(self, account_view: AccountView) -> None:
        """flush() does not affect already closed trades."""
        builder = FlatToFlatTradeBuilder()

        buy = _fill("f-1", order_id="o-b1", quantity=100, price=10.0, fee=5.0)
        sell = _fill(
            "f-2",
            order_id="o-s1",
            direction=OrderSide.SELL,
            quantity=100,
            price=11.0,
            fee=5.0,
            event_time=datetime(2026, 3, 5),
        )

        builder.on_fill(buy, account_view)
        builder.on_fill(sell, account_view)
        builder.flush()

        closed = builder.get_closed_trades()
        assert len(closed) == 1


# ---------------------------------------------------------------------------
# FlatToFlatTradeBuilder — multi-instrument isolation
# ---------------------------------------------------------------------------


class TestFlatToFlatMultiInstrument:
    def test_instruments_tracked_independently(self, account_view: AccountView) -> None:
        """Buy A + Buy B, sell A → only A closes, B remains open."""
        builder = FlatToFlatTradeBuilder()

        buy_a = _fill(
            "f-1",
            order_id="o-a1",
            instrument_id=2,
            quantity=100,
            price=10.0,
            fee=5.0,
        )
        buy_b = _fill(
            "f-2",
            order_id="o-b1",
            instrument_id=3,
            quantity=200,
            price=20.0,
            fee=10.0,
        )
        sell_a = _fill(
            "f-3",
            order_id="o-a2",
            instrument_id=2,
            direction=OrderSide.SELL,
            quantity=100,
            price=11.0,
            fee=5.0,
            event_time=datetime(2026, 3, 5),
        )

        builder.on_fill(buy_a, account_view)
        builder.on_fill(buy_b, account_view)
        builder.on_fill(sell_a, account_view)

        closed = builder.get_closed_trades()
        assert len(closed) == 1
        assert closed[0].instrument_id == 2

        open_trades = builder.get_open_trades()
        assert len(open_trades) == 1
        assert open_trades[0].instrument_id == 3
        assert open_trades[0].quantity == 200


# ---------------------------------------------------------------------------
# FlatToFlatTradeBuilder — sell with no open position
# ---------------------------------------------------------------------------


class TestFlatToFlatExcessSell:
    def test_sell_without_buy_is_noop(self, account_view: AccountView) -> None:
        """Sell with no open position → no-op, no trades created."""
        builder = FlatToFlatTradeBuilder()

        sell = _fill(
            "f-1",
            order_id="o-s1",
            direction=OrderSide.SELL,
            quantity=100,
            price=11.0,
            fee=5.0,
        )
        builder.on_fill(sell, account_view)

        assert builder.get_closed_trades() == ()
        assert builder.get_open_trades() == ()

    def test_sell_exceeding_net_position_caps_at_zero(
        self, account_view: AccountView
    ) -> None:
        """Buy 100, sell 200 → sell 100 closes, excess 100 ignored."""
        builder = FlatToFlatTradeBuilder()

        buy = _fill(
            "f-1",
            order_id="o-b1",
            quantity=100,
            price=10.0,
            fee=5.0,
            event_time=datetime(2026, 3, 1),
        )
        sell = _fill(
            "f-2",
            order_id="o-s1",
            direction=OrderSide.SELL,
            quantity=200,
            price=12.0,
            fee=6.0,
            event_time=datetime(2026, 3, 5),
        )

        builder.on_fill(buy, account_view)
        builder.on_fill(sell, account_view)

        closed = builder.get_closed_trades()
        assert len(closed) == 1
        # Only 100 matched, VWAP entry=10, VWAP exit=12
        assert closed[0].entry_price == pytest.approx(10.0)
        assert closed[0].exit_price == pytest.approx(12.0)
        assert closed[0].quantity == 100
        assert closed[0].gross_pnl == pytest.approx(200.0)
        # fees: buy 5.0, sell proportional: 6.0 * 100/200 = 3.0
        assert closed[0].fees == pytest.approx(8.0)
        assert closed[0].net_pnl == pytest.approx(192.0)

        assert builder.get_open_trades() == ()


# ---------------------------------------------------------------------------
# FlatToFlatTradeBuilder — fee accumulation
# ---------------------------------------------------------------------------


class TestFlatToFlatFees:
    def test_fees_accumulated_across_multiple_fills(
        self, account_view: AccountView
    ) -> None:
        """Multiple buys and sells accumulate all fees."""
        builder = FlatToFlatTradeBuilder()

        buy1 = _fill(
            "f-1",
            order_id="o-b1",
            quantity=100,
            price=10.0,
            fee=3.0,
            event_time=datetime(2026, 3, 1),
        )
        buy2 = _fill(
            "f-2",
            order_id="o-b2",
            quantity=100,
            price=12.0,
            fee=4.0,
            event_time=datetime(2026, 3, 2),
        )
        sell1 = _fill(
            "f-3",
            order_id="o-s1",
            direction=OrderSide.SELL,
            quantity=100,
            price=13.0,
            fee=3.5,
            event_time=datetime(2026, 3, 5),
        )
        sell2 = _fill(
            "f-4",
            order_id="o-s2",
            direction=OrderSide.SELL,
            quantity=100,
            price=14.0,
            fee=4.5,
            event_time=datetime(2026, 3, 6),
        )

        builder.on_fill(buy1, account_view)
        builder.on_fill(buy2, account_view)
        builder.on_fill(sell1, account_view)
        builder.on_fill(sell2, account_view)

        closed = builder.get_closed_trades()
        assert len(closed) == 1
        # total fees: 3 + 4 + 3.5 + 4.5 = 15
        assert closed[0].fees == pytest.approx(15.0)
        # gross: (100*13 + 100*14) - (100*10 + 100*12) = 2700 - 2200 = 500
        assert closed[0].gross_pnl == pytest.approx(500.0)
        assert closed[0].net_pnl == pytest.approx(485.0)
