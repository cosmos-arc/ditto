"""Cash entitlement, payment and personal-share tax through the account boundary."""

from datetime import date, datetime

import pytest
from ditto_kernel.identity import InstrumentId
from ditto_kernel.order import OrderSide
from ditto_portfolio.accounting.account import Account
from ditto_portfolio.accounting.cash import CashBook
from ditto_portfolio.accounting.dividends import StockDistribution
from ditto_portfolio.accounting.fills import FillEvent


def trade(account: Account, day: str, side: OrderSide, quantity: int, price: float):
    account.apply_fill(
        FillEvent(
            day,
            day,
            InstrumentId(1),
            side,
            quantity,
            price,
            0,
            0,
            datetime.fromisoformat(day),
            quantity,
            0,
        ),
        day,
    )
    if side == OrderSide.BUY:
        account.thaw_position(InstrumentId(1), quantity)
    account.mark_to_market({InstrumentId(1): price})


@pytest.mark.pit
def test_future_event_cannot_leak_acquisition_lots_or_book_clocks():
    event = StockDistribution(
        InstrumentId(1),
        date(2020, 6, 10),
        date(2020, 6, 11),
        date(2020, 6, 12),
        999,
        date(2020, 6, 5),
        "snapshot:future",
    )
    accounts = [
        Account(cash=CashBook(2000, 2000, 0), dividends=events)
        for events in ((), (event,))
    ]
    for account in accounts:
        account.settle_dividends("2020-06-04")
        trade(account, "2020-06-04", OrderSide.BUY, 100, 10)
        account.close_dividend_day("2020-06-04")
    assert accounts[0].get_view() == accounts[1].get_view()
    accounts[1].settle_dividends("2020-06-08")
    assert accounts[1].get_view().dividends.events == (event,)
    assert accounts[1].get_view().dividends.lots[0].acquired == date(2020, 6, 4)


def test_repeated_session_closes_use_final_net_holdings_and_tax():
    event = StockDistribution(
        InstrumentId(1),
        date(2020, 6, 2),
        date(2020, 6, 3),
        date(2020, 6, 5),
        1,
        date(2020, 5, 28),
        "snapshot:cash",
    )
    account = Account(cash=CashBook(3000, 3000, 0), dividends=(event,))
    trade(account, "2020-06-02", OrderSide.BUY, 100, 10)
    account.close_dividend_day("2020-06-02")
    trade(account, "2020-06-02", OrderSide.BUY, 100, 10)
    account.close_dividend_day("2020-06-02")
    assert sum(r.quantity for r in account.get_view().dividends.rights) == 200
    account.settle_dividends("2020-06-03")
    trade(account, "2020-06-03", OrderSide.SELL, 100, 9)
    account.close_dividend_day("2020-06-03")
    assert account.get_view().dividends.tax_payable == 20
    trade(account, "2020-06-03", OrderSide.BUY, 50, 9)
    account.close_dividend_day("2020-06-03")
    view = account.get_view()
    assert (view.dividends.tax_payable, view.cash.frozen, view.cash.available) == (
        10,
        10,
        1440,
    )
    assert sum(r.remaining for r in view.dividends.rights) == 150


def test_dividend_receivable_cannot_be_spent_and_payment_is_idempotent():
    event = StockDistribution(
        instrument_id=InstrumentId(1),
        record_date=date(2020, 6, 2),
        ex_date=date(2020, 6, 3),
        pay_date=date(2020, 6, 5),
        gross_per_share=1.0,
        announcement_date=date(2020, 5, 28),
        source_snapshot_id="snapshot:dividend:1",
    )
    account = Account(cash=CashBook(2000, 2000, 0), dividends=(event, event))
    trade(account, "2020-06-02", OrderSide.BUY, 100, 10)
    account.close_dividend_day("2020-06-02")
    account.settle_dividends("2020-06-03")
    assert account.get_view().nav == 2000
    account.mark_to_market({InstrumentId(1): 9})
    view = account.get_view()
    assert (view.cash.available, view.dividends.receivable, view.nav) == (
        1000,
        100,
        2000,
    )
    # Selling after record date keeps the right, with 20 CNY tax reserved.
    trade(account, "2020-06-03", OrderSide.SELL, 100, 9)
    account.close_dividend_day("2020-06-03")
    assert account.get_view().nav == 1980
    account.settle_dividends("2020-06-04")
    assert account.cash.available == 1880
    account.settle_dividends("2020-06-05")
    account.settle_dividends("2020-06-05")
    assert account.cash.available == 1980
    assert account.get_view().dividends.receivable == 0
    assert account.get_view().dividends.entries[-1].amount == 100


@pytest.mark.parametrize(
    ("sell_date", "expected_tax"),
    [
        ("2014-02-28", 20),
        ("2014-03-01", 10),
        ("2015-01-31", 10),
        ("2015-02-01", 5),
    ],
)
def test_calendar_month_year_tax_boundaries(sell_date, expected_tax):
    from ditto_portfolio.accounting.dividends import dividend_tax_rate

    assert (
        dividend_tax_rate(
            date(2014, 1, 31), date.fromisoformat(sell_date), date(2014, 2, 10)
        )
        * 100
        == expected_tax
    )


def test_partial_sale_uses_oldest_lot_without_taxing_the_entire_entitlement():
    event = StockDistribution(
        InstrumentId(1),
        date(2020, 6, 2),
        date(2020, 6, 3),
        date(2020, 6, 5),
        1,
        date(2020, 5, 28),
        "snapshot:dividend:partial",
    )
    account = Account(cash=CashBook(3000, 3000, 0), dividends=(event,))
    trade(account, "2019-05-01", OrderSide.BUY, 100, 10)
    account.close_dividend_day("2019-05-01")
    trade(account, "2020-06-02", OrderSide.BUY, 100, 10)
    account.close_dividend_day("2020-06-02")
    account.settle_dividends("2020-06-03")
    trade(account, "2020-06-03", OrderSide.SELL, 150, 9)
    account.close_dividend_day("2020-06-03")
    assert account.get_view().nav == 2990
    assert account.get_view().dividends.tax_payable == 10
    taxed = account.get_view().dividends.entries[-1]
    assert (taxed.quantity, taxed.acquired, taxed.amount) == (50, "2020-06-02", -10)
    account.settle_dividends("2020-06-05")
    assert account.cash.available == 2540
    assert account.get_view().dividends.receivable == 0


def test_share_distribution_preserves_cost_and_waits_for_listing_before_sale():
    """100 at 12 becomes 150 at 8; the 50 new shares unlock on their own date."""
    event = StockDistribution(
        InstrumentId(1),
        date(2020, 6, 2),
        date(2020, 6, 3),
        date(2020, 6, 3),
        0,
        date(2020, 5, 28),
        "snapshot:shares",
        share_ratio=0.5,
        listing_date=date(2020, 6, 5),
        taxable_share_income=0,
        share_tax_basis="issuer:premium-capital-reserve",
    )
    account = Account(cash=CashBook(2000, 2000, 0), dividends=(event, event))
    trade(account, "2020-06-02", OrderSide.BUY, 100, 12)
    account.close_dividend_day("2020-06-02")
    account.settle_dividends("2020-06-03")
    view = account.get_view()
    position = view.positions[InstrumentId(1)]
    assert (position.quantity, position.available_quantity, position.average_cost) == (
        150,
        100,
        8,
    )
    assert (view.cash.available, view.nav) == (800, 2000)
    account.settle_dividends("2020-06-03")
    account.mark_to_market({InstrumentId(1): 8})
    account.close_dividend_day("2020-06-03")
    assert account.get_view().nav == 2000
    account.settle_dividends("2020-06-04")
    assert account.positions[InstrumentId(1)].available_quantity == 100
    account.close_dividend_day("2020-06-04")
    account.settle_dividends("2020-06-05")
    account.settle_dividends("2020-06-05")
    position = account.positions[InstrumentId(1)]
    assert (position.quantity, position.available_quantity) == (150, 150)
    trade(account, "2020-06-05", OrderSide.SELL, 150, 8)
    account.close_dividend_day("2020-06-05")
    assert (account.cash.available, account.get_view().nav) == (2000, 2000)


def test_same_day_share_credit_and_buy_form_one_tax_acquisition_lot():
    first = StockDistribution(
        InstrumentId(1),
        date(2020, 6, 2),
        date(2020, 6, 3),
        None,
        0,
        date(2020, 5, 28),
        "source:shares",
        share_ratio=1,
        listing_date=date(2020, 6, 3),
        share_tax_basis="issuer:premium-capital",
    )
    second = StockDistribution(
        InstrumentId(1),
        date(2020, 6, 4),
        date(2020, 6, 5),
        date(2020, 6, 5),
        1,
        date(2020, 6, 1),
        "source:cash",
    )
    account = Account(cash=CashBook(5000, 5000, 0), dividends=(first, second))
    trade(account, "2020-06-02", OrderSide.BUY, 100, 10)
    account.close_dividend_day("2020-06-02")
    account.settle_dividends("2020-06-03")
    trade(account, "2020-06-03", OrderSide.BUY, 100, 5)
    account.close_dividend_day("2020-06-03")
    account.settle_dividends("2020-06-04")
    account.close_dividend_day("2020-06-04")
    account.settle_dividends("2020-06-05")
    trade(account, "2020-06-05", OrderSide.SELL, 200, 4)
    account.close_dividend_day("2020-06-05")
    # 200 old/new shares disposed, each earned CNY 1: 20% tax is CNY 40.
    assert account.get_view().dividends.tax_payable == 40


def test_initial_share_tax_reduces_receivable_before_payment_not_available_cash():
    event = StockDistribution(
        InstrumentId(1),
        date(2014, 6, 2),
        date(2014, 6, 3),
        date(2014, 6, 5),
        1,
        date(2014, 5, 28),
        "source:bonus",
        share_ratio=0.5,
        listing_date=date(2014, 6, 4),
        taxable_share_income=0.5,
        share_tax_basis="issuer:bonus-at-par",
    )
    account = Account(cash=CashBook(2000, 2000, 0), dividends=(event,))
    trade(account, "2014-06-02", OrderSide.BUY, 100, 10)
    account.close_dividend_day("2014-06-02")
    account.settle_dividends("2014-06-03")
    view = account.get_view()
    assert (view.cash.available, view.dividends.receivable, view.nav) == (
        1000,
        92.5,
        1992.5,
    )
    account.settle_dividends("2014-06-05")
    account.settle_dividends("2014-06-05")
    view = account.get_view()
    assert (view.cash.available, view.dividends.receivable, view.nav) == (
        1092.5,
        0,
        1992.5,
    )
    taxes = [e for e in view.dividends.entries if e.kind == "share_tax_payment"]
    assert [(e.day, e.amount) for e in taxes] == [("2014-06-05", -2.5)]


def test_fractional_entitlement_refuses_atomically_and_revised_close_can_retry():
    event = StockDistribution(
        InstrumentId(1),
        date(2020, 6, 2),
        date(2020, 6, 3),
        None,
        0,
        date(2020, 5, 28),
        "source:fraction",
        share_ratio=0.5,
        listing_date=date(2020, 6, 3),
        share_tax_basis="issuer:premium-capital",
    )
    account = Account(cash=CashBook(2000, 2000, 0), dividends=(event,))
    trade(account, "2020-06-02", OrderSide.BUY, 1, 12)
    before = account.get_view()
    with pytest.raises(ValueError, match="fractional share allocation"):
        account.close_dividend_day("2020-06-02")
    assert account.get_view() == before
    trade(account, "2020-06-02", OrderSide.BUY, 1, 12)
    account.close_dividend_day("2020-06-02")
    account.settle_dividends("2020-06-03")
    assert account.positions[InstrumentId(1)].quantity == 3


@pytest.mark.parametrize("buy_day", ["2020-06-04", "2020-06-08"])
def test_tax_fifo_cannot_dispose_unlisted_shares_before_later_buys(buy_day):
    first = StockDistribution(
        InstrumentId(1),
        date(2020, 6, 3),
        date(2020, 6, 4),
        None,
        0,
        date(2020, 5, 28),
        "source:locked",
        share_ratio=1,
        listing_date=date(2020, 6, 12),
        share_tax_basis="issuer",
    )
    second = StockDistribution(
        InstrumentId(1),
        date(2020, 6, 30),
        date(2020, 7, 1),
        date(2020, 7, 1),
        1,
        date(2020, 6, 20),
        "source:cash",
    )
    account = Account(cash=CashBook(5000, 5000, 0), dividends=(first, second))
    trade(account, "2020-06-03", OrderSide.BUY, 100, 10)
    account.close_dividend_day("2020-06-03")
    account.settle_dividends("2020-06-04")
    trade(account, "2020-06-04", OrderSide.SELL, 100, 5)
    account.close_dividend_day("2020-06-04")
    account.settle_dividends(buy_day)
    trade(account, buy_day, OrderSide.BUY, 100, 5)
    account.close_dividend_day(buy_day)
    account.settle_dividends("2020-06-09")
    trade(account, "2020-06-09", OrderSide.SELL, 100, 5)
    account.close_dividend_day("2020-06-09")
    book = account.get_view().dividends
    assert [(lot.acquired, lot.quantity) for lot in book.lots] == [
        (date(2020, 6, 4), 100)
    ]
    assert book.lots[0].available_from == date(2020, 6, 12)
    assert book.unlisted_shares(InstrumentId(1)) == 100
    account.settle_dividends("2020-06-12")
    assert account.get_view().dividends.unlisted_shares(InstrumentId(1)) == 0
    account.close_dividend_day("2020-06-30")
    account.settle_dividends("2020-07-01")
    trade(account, "2020-07-06", OrderSide.SELL, 100, 4)
    account.close_dividend_day("2020-07-06")
    assert account.get_view().dividends.tax_payable == 10
