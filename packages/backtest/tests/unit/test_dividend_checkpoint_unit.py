"""Checkpoint and persisted report retain the same unspent entitlement."""

from datetime import date
from typing import Any

import pytest
from ditto_backtest.audit.collector import ExecutionAuditCollector
from ditto_backtest.audit.state import ExecutionAuditStateSnapshot
from ditto_backtest.brokerage import BacktestBrokerage
from ditto_backtest.result import (
    BacktestAccountStateSnapshot,
    BacktestFrozenQuantitySnapshot,
    BacktestSettlementStateSnapshot,
)
from ditto_execution.orders.book import OrderBook
from ditto_execution.orders.journal import InMemoryOrderEventJournal
from ditto_kernel.identity import InstrumentId
from ditto_portfolio.accounting.account import Account
from ditto_portfolio.accounting.cash import CashBook
from ditto_portfolio.accounting.dividends import Distribution
from ditto_portfolio.accounting.position import Position


@pytest.mark.parametrize("asset_class", ["stock", "etf"])
def test_saved_receivable_and_fifo_tax_resume_without_second_payment(asset_class):
    event = Distribution(
        InstrumentId(1),
        date(2020, 6, 2),
        date(2020, 6, 3),
        date(2020, 6, 5),
        1,
        date(2020, 5, 20),
        "snapshot:cash",
        asset_class=asset_class,
    )
    from ditto_portfolio.accounting.dividends import DividendBook

    book = DividendBook.start((event,)).close("2020-06-02", {InstrumentId(1): 100})
    account = Account(
        cash=CashBook(1000, 1000, 0),
        positions={
            InstrumentId(1): Position(InstrumentId(1), 100, 100, 10, 1000, 0, 0, 0)
        },
        dividend_state=book,
    )
    account.settle_dividends("2020-06-03")
    snapshot = BacktestAccountStateSnapshot.from_account_view(account.get_view())
    restored = BacktestAccountStateSnapshot.from_json(snapshot.to_json())
    assert restored.dividends.events[0].asset_class == asset_class
    assert restored.dividends.receivable == 100
    assert restored.state_hash == snapshot.state_hash
    resumed = Account(
        cash=account.cash,
        positions=dict(account.positions),
        dividend_state=restored.dividends,
    )
    resumed.settle_dividends("2020-06-05")
    resumed.settle_dividends("2020-06-05")
    assert resumed.get_view().nav == 2000
    assert resumed.cash.available == 1100
    collector = ExecutionAuditCollector()
    collector.record_account_view("2020-06-03", account.get_view())
    stored = ExecutionAuditStateSnapshot.from_canonical_json(
        collector.snapshot_state().to_json()
    )
    assert stored.to_daily_snapshots()[0][1].dividends.receivable == 100


@pytest.mark.pit
def test_future_dividend_is_not_visible_to_the_strategy_account_view():
    event = Distribution(
        InstrumentId(1),
        date(2020, 6, 10),
        date(2020, 6, 11),
        date(2020, 6, 12),
        999,
        date(2020, 6, 5),
        "snapshot:future",
    )
    account = Account(cash=CashBook(1000, 1000, 0), dividends=(event,))
    account.settle_dividends("2020-06-04")
    assert account.get_view().dividends.events == ()
    assert account.get_view().nav == 1000
    account.settle_dividends("2020-06-08")
    assert account.get_view().dividends.events == (event,)


def test_saved_unlisted_shares_unlock_once_after_restore():
    from dataclasses import replace

    from ditto_portfolio.accounting.dividends import DividendBook

    event = Distribution(
        InstrumentId(1),
        date(2020, 6, 2),
        date(2020, 6, 3),
        None,
        0,
        date(2020, 5, 20),
        "snapshot:shares",
        share_ratio=0.5,
        listing_date=date(2020, 6, 5),
        share_tax_basis="issuer:premium-capital",
    )
    book = DividendBook.start((event,)).close("2020-06-02", {InstrumentId(1): 100})
    account = Account(
        cash=CashBook(800, 800, 0),
        positions={
            InstrumentId(1): Position(InstrumentId(1), 100, 100, 12, 1200, 0, 0, 0)
        },
        dividend_state=book,
    )
    account.settle_dividends("2020-06-03")
    snapshot = BacktestAccountStateSnapshot.from_account_view(account.get_view())
    restored = BacktestAccountStateSnapshot.from_json(snapshot.to_json())
    assert restored.state_hash == snapshot.state_hash
    resumed = Account(
        cash=account.cash,
        positions=dict(account.positions),
        dividend_state=restored.dividends,
    )
    resumed.settle_dividends("2020-06-04")
    assert resumed.positions[InstrumentId(1)].available_quantity == 100
    resumed.settle_dividends("2020-06-05")
    resumed.settle_dividends("2020-06-05")
    assert resumed.positions[InstrumentId(1)] == replace(
        account.positions[InstrumentId(1)], available_quantity=150
    )
    assert resumed.get_view().nav == 2000


@pytest.mark.parametrize("method", ["fifo", "flat_to_flat"])
def test_trade_matching_survives_share_credit_restore_and_listing(method):
    from datetime import datetime

    from ditto_backtest._trade_builder_checkpoint import (
        trade_builder_from_payload,
        trade_builder_to_payload,
    )
    from ditto_execution.trade_builder import FifoTradeBuilder, FlatToFlatTradeBuilder
    from ditto_kernel.order import OrderSide
    from ditto_portfolio.accounting.dividends import DividendBook
    from ditto_portfolio.accounting.fills import FillEvent

    factory = FifoTradeBuilder if method == "fifo" else FlatToFlatTradeBuilder
    builder = factory()
    account = Account(cash=CashBook(5000, 5000, 0))

    def fill(day, side, quantity, price):
        item = FillEvent(
            day,
            day,
            InstrumentId(1),
            side,
            quantity,
            price,
            6 if day == "2020-06-02" else 0,
            0,
            datetime.fromisoformat(day),
            quantity,
            0,
        )
        builder.on_fill(item, account.get_view())

    fill("2020-06-02", OrderSide.BUY, 100, 12)
    event = Distribution(
        InstrumentId(1),
        date(2020, 6, 2),
        date(2020, 6, 3),
        None,
        0,
        date(2020, 5, 20),
        "source:shares",
        share_ratio=0.5,
        listing_date=date(2020, 6, 5),
        share_tax_basis="issuer",
    )
    book, _ = (
        DividendBook.start((event,))
        .close("2020-06-02", {InstrumentId(1): 100})
        .settle("2020-06-03")
    )
    builder.apply_distributions(book)
    saved = trade_builder_from_payload(
        trade_builder_to_payload(builder.snapshot_state()), strict=True
    )
    builder = factory()
    builder.restore_state(saved)
    builder.apply_distributions(book)
    assert sum(t.quantity for t in builder.get_open_trades()) == 150
    fill("2020-06-03", OrderSide.BUY, 100, 8)
    fill("2020-06-03", OrderSide.SELL, 100, 8)
    fill("2020-06-04", OrderSide.SELL, 100, 8)
    if method == "fifo":
        locked = builder.snapshot_state().fifo_open_entries
        assert len(locked) == 1
        assert locked[0].available_from == date(2020, 6, 5)
    fill("2020-06-05", OrderSide.SELL, 50, 8)
    assert sum(t.quantity for t in builder.get_closed_trades()) == 250
    gross_pnls = [t.gross_pnl for t in builder.get_closed_trades()]
    assert None not in gross_pnls
    assert sum(pnl for pnl in gross_pnls if pnl is not None) == pytest.approx(0)
    assert builder.get_open_trades() == ()
    assert sum(t.fees for t in builder.get_closed_trades()) == pytest.approx(6)


def test_fifo_attributes_whole_share_credit_across_fractional_cost_lots():
    from datetime import datetime

    from ditto_execution.trade_builder import FifoTradeBuilder
    from ditto_kernel.order import OrderSide
    from ditto_portfolio.accounting.dividends import DividendBook
    from ditto_portfolio.accounting.fills import FillEvent

    builder = FifoTradeBuilder()
    account = Account(cash=CashBook(100, 100, 0))
    for day, price, fee in [("2020-06-01", 10, 1), ("2020-06-02", 20, 2)]:
        builder.on_fill(
            FillEvent(
                day,
                day,
                InstrumentId(1),
                OrderSide.BUY,
                1,
                price,
                fee,
                0,
                datetime.fromisoformat(day),
                1,
                0,
            ),
            account.get_view(),
        )
    event = Distribution(
        InstrumentId(1),
        date(2020, 6, 2),
        date(2020, 6, 3),
        None,
        0,
        date(2020, 5, 20),
        "source:shares",
        share_ratio=0.5,
        listing_date=date(2020, 6, 5),
        share_tax_basis="issuer",
    )
    book, _ = (
        DividendBook.start((event,))
        .close("2020-06-02", {InstrumentId(1): 2})
        .settle("2020-06-03")
    )
    builder.apply_distributions(book)
    assert sum(t.quantity for t in builder.get_open_trades()) == 3
    builder.on_fill(
        FillEvent(
            "sell",
            "sell",
            InstrumentId(1),
            OrderSide.SELL,
            3,
            10,
            0,
            0,
            datetime(2020, 6, 5),
            3,
            0,
        ),
        account.get_view(),
    )
    assert sum(t.quantity for t in builder.get_closed_trades()) == 3
    gross_pnls = [t.gross_pnl for t in builder.get_closed_trades()]
    assert None not in gross_pnls
    assert sum(pnl for pnl in gross_pnls if pnl is not None) == pytest.approx(0)
    assert sum(t.fees for t in builder.get_closed_trades()) == pytest.approx(3)


def test_share_conversion_checkpoint_resume_never_converts_twice():
    from ditto_portfolio.accounting.conversions import ShareConversion

    conversion = ShareConversion(
        InstrumentId(1),
        date(2020, 6, 3),
        4.0,
        date(2020, 5, 28),
        "config:etf-share-conversions:snap",
    )
    account = Account(
        cash=CashBook(5000, 5000, 0),
        positions={
            InstrumentId(1): Position(InstrumentId(1), 100, 0, 2.384, 238.4, 0, 0, 0)
        },
        conversions=(conversion,),
    )
    brokerage = BacktestBrokerage(
        account=account,
        order_book=OrderBook(journal=InMemoryOrderEventJournal()),
    )
    # 100 shares bought on 06-02 stay T+1-frozen through the conversion open.
    brokerage.restore_settlement_state(
        BacktestSettlementStateSnapshot(
            frozen_quantities=(
                BacktestFrozenQuantitySnapshot(InstrumentId(1), "2020-06-03", 100),
            )
        )
    )
    brokerage.settle("2020-06-03")
    position = account.positions[InstrumentId(1)]
    assert position.quantity == 400
    assert position.available_quantity == 400
    assert position.average_cost == pytest.approx(2.384 / 4)
    assert account.get_view().nav == pytest.approx(5000 + 400 * 2.384 / 4)

    snapshot = BacktestAccountStateSnapshot.from_account_view(account.get_view())
    restored = BacktestAccountStateSnapshot.from_json(snapshot.to_json())
    assert restored.state_hash == snapshot.state_hash
    assert restored.dividends.conversions == (conversion,)
    assert restored.dividends.entries[-1].kind == "share_conversion"
    resumed = Account(
        cash=account.cash,
        positions=dict(account.positions),
        dividend_state=restored.dividends,
    )
    resumed.settle_dividends("2020-06-04")
    resumed.apply_share_conversions("2020-06-04")
    assert resumed.positions[InstrumentId(1)].quantity == 400


def test_conflicting_conversion_checkpoint_fails_closed():
    from ditto_portfolio.accounting.conversions import ShareConversion

    conversion = ShareConversion(
        InstrumentId(1),
        date(2020, 6, 3),
        4.0,
        date(2020, 5, 28),
        "config:etf-share-conversions:snap",
    )
    declared = {
        "instrument_id": 1,
        "effective_date": "2020-06-03",
        "ratio": 4.0,
        "announcement_date": "2020-05-28",
        "source_snapshot_id": "config:etf-share-conversions:snap",
        "source_ticker": "159941.SZ",
        "rounding_note": "1:4 whole-split",
    }
    account = Account(cash=CashBook(10, 10, 0), conversions=(conversion,))
    payload: dict[str, Any] = BacktestAccountStateSnapshot.from_account_view(
        account.get_view()
    ).to_payload()
    payload["dividends"]["conversions"] = [
        declared,
        {**declared, "ratio": 2.0},
    ]
    with pytest.raises(ValueError, match="conflicting conversion revision"):
        BacktestAccountStateSnapshot.from_payload(payload)
