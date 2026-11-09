"""Cash entitlement, payment and personal-share tax through the account boundary."""

from datetime import date, datetime

import pytest
from ditto_kernel.identity import InstrumentId
from ditto_kernel.order import OrderSide
from ditto_portfolio.accounting.account import Account
from ditto_portfolio.accounting.cash import CashBook
from ditto_portfolio.accounting.dividends import CashDividend
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
    event = CashDividend(
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
    event = CashDividend(
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
    event = CashDividend(
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
    event = CashDividend(
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
