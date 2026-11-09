"""Checkpoint and persisted report retain the same unspent entitlement."""

from datetime import date

import pytest
from ditto_backtest.audit.collector import ExecutionAuditCollector
from ditto_backtest.audit.state import ExecutionAuditStateSnapshot
from ditto_backtest.result import BacktestAccountStateSnapshot
from ditto_kernel.identity import InstrumentId
from ditto_portfolio.accounting.account import Account
from ditto_portfolio.accounting.cash import CashBook
from ditto_portfolio.accounting.dividends import StockDistribution
from ditto_portfolio.accounting.position import Position


def test_saved_receivable_and_fifo_tax_resume_without_second_payment():
    event = StockDistribution(
        InstrumentId(1),
        date(2020, 6, 2),
        date(2020, 6, 3),
        date(2020, 6, 5),
        1,
        date(2020, 5, 20),
        "snapshot:cash",
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
    event = StockDistribution(
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

    event = StockDistribution(
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
