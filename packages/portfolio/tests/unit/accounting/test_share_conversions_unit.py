"""Declared ETF share conversions rescale holdings without cash or tax (#762)."""

from dataclasses import replace
from datetime import date, datetime

import pytest
from ditto_kernel.identity import InstrumentId
from ditto_kernel.order import OrderSide
from ditto_portfolio.accounting.account import Account
from ditto_portfolio.accounting.cash import CashBook
from ditto_portfolio.accounting.conversions import ShareConversion
from ditto_portfolio.accounting.dividends import DividendBook
from ditto_portfolio.accounting.fills import FillEvent

_IID = InstrumentId(2_000_941)


def _conversion(**overrides: object) -> ShareConversion:
    facts: dict[str, object] = {
        "instrument_id": _IID,
        "effective_date": date(2022, 7, 5),
        "ratio": 4.0,
        "announcement_date": date(2022, 6, 29),
        "source_snapshot_id": "config:etf-share-conversions:snap1",
        "source_ticker": "159941.SZ",
        "rounding_note": "1:4 整倍拆分、持有人份额恒整数、无碎份",
    }
    return ShareConversion(**{**facts, **overrides})


def trade(
    account: Account, day: str, side: OrderSide, quantity: int, price: float
) -> None:
    account.apply_fill(
        FillEvent(
            day,
            day,
            _IID,
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
        account.thaw_position(_IID, quantity)
    account.mark_to_market({_IID: price})
    account.close_dividend_day(day)


def test_conversion_rejects_unknown_or_inconsistent_facts() -> None:
    assert _conversion().identity == f"{int(_IID)}:2022-07-05"
    assert _conversion().converted(3_537_052_541) == 14_148_210_164
    for overrides in (
        {"ratio": 0.0},
        {"ratio": -4.0},
        {"ratio": 1.0},
        {"ratio": float("nan")},
        {"ratio": float("inf")},
        {"announcement_date": date(2022, 7, 5)},
        {"effective_date": date(2022, 6, 29)},
        {"source_snapshot_id": ""},
        {"instrument_id": InstrumentId(0)},
    ):
        with pytest.raises(ValueError, match="unknown/invalid share conversion"):
            _conversion(**overrides)


def test_fractional_conversion_requires_evidence() -> None:
    with pytest.raises(ValueError, match="fractional conversion requires evidence"):
        _conversion(ratio=1.5).converted(3)
    assert _conversion(ratio=0.5).converted(6) == 3


def test_conflicting_conversion_identity_is_rejected() -> None:
    with pytest.raises(ValueError, match="conflicting conversion revision"):
        DividendBook.start((), conversions=(_conversion(), _conversion(ratio=2.0)))
    # Identical duplicate declarations collapse without a second entitlement.
    assert DividendBook.start((), conversions=(_conversion(), _conversion())) == (
        DividendBook(conversions=(_conversion(),))
    )


def test_effective_day_rescales_quantity_and_cost_without_cash() -> None:
    account = Account(cash=CashBook(10_000, 10_000, 0), conversions=(_conversion(),))
    trade(account, "2022-07-04", OrderSide.BUY, 100, 2.384)
    before = account.get_view()
    account.settle_dividends("2022-07-05")
    applied = account.apply_share_conversions("2022-07-05")
    assert applied == (_conversion(),)
    position = account.get_view().positions[_IID]
    assert position.quantity == 400
    assert position.available_quantity == 400
    assert position.average_cost == pytest.approx(2.384 / 4)
    assert position.quantity * position.average_cost == pytest.approx(238.4)
    assert position.market_value == pytest.approx(before.positions[_IID].market_value)
    assert account.get_view().cash.available == before.cash.available
    assert account.get_view().nav == pytest.approx(before.nav)
    entry = account.get_view().dividends.entries[-1]
    assert entry.kind == "share_conversion"
    assert entry.amount == 0.0
    assert entry.quantity == 300
    # Re-settling the same session and the next session never converts twice.
    assert account.apply_share_conversions("2022-07-05") == ()
    account.close_dividend_day("2022-07-05")
    account.settle_dividends("2022-07-06")
    assert account.apply_share_conversions("2022-07-06") == ()
    assert account.get_view().positions[_IID].quantity == 400


def test_conversion_waits_for_effective_date_and_skips_empty_positions() -> None:
    account = Account(cash=CashBook(100, 100, 0), conversions=(_conversion(),))
    account.settle_dividends("2022-07-04")
    assert account.apply_share_conversions("2022-07-04") == ()
    assert _IID not in account.get_view().positions
    account.settle_dividends("2022-07-05")
    # No holdings at the effective date: the event is still consumed once,
    # with a zero-quantity entry, so later acquisitions never rescale.
    assert account.apply_share_conversions("2022-07-05") == (_conversion(),)
    assert account.get_view().dividends.entries[-1].quantity == 0
    account.close_dividend_day("2022-07-05")
    # Acquiring after the conversion trades post-conversion shares only.
    trade(account, "2022-07-05", OrderSide.BUY, 100, 0.596)
    account.settle_dividends("2022-07-06")
    assert account.apply_share_conversions("2022-07-06") == ()
    assert account.get_view().positions[_IID].quantity == 100


def test_frozen_shares_and_average_cost_rescale_together() -> None:
    account = Account(cash=CashBook(10_000, 10_000, 0), conversions=(_conversion(),))
    # Bought one session before the conversion; still T+1 frozen at the open.
    account.apply_fill(
        FillEvent(
            "2022-07-04",
            "2022-07-04",
            _IID,
            OrderSide.BUY,
            100,
            2.384,
            0,
            0,
            datetime.fromisoformat("2022-07-04T15:00:00"),
            100,
            0,
        ),
        "2022-07-04",
    )
    account.mark_to_market({_IID: 2.384})
    account.close_dividend_day("2022-07-04")
    assert account.get_view().positions[_IID].available_quantity == 0
    account.settle_dividends("2022-07-05")
    account.apply_share_conversions("2022-07-05")
    position = account.get_view().positions[_IID]
    assert position.quantity == 400
    assert position.available_quantity == 0
    assert position.average_cost == pytest.approx(0.596)


def test_view_hides_unannounced_conversions() -> None:
    conversion = _conversion(announcement_date=date(2022, 7, 1))
    account = Account(cash=CashBook(10_000, 10_000, 0), conversions=(conversion,))
    trade(account, "2022-07-04", OrderSide.BUY, 100, 2.384)
    visible = account.get_view()
    assert visible.dividends.conversions == (conversion,)
    # Announced during the shown session: still hidden until the next day.
    hidden = replace(
        conversion, announcement_date=date(2022, 7, 4), effective_date=date(2022, 7, 6)
    )
    account = Account(cash=CashBook(10_000, 10_000, 0), conversions=(hidden,))
    trade(account, "2022-07-04", OrderSide.BUY, 100, 2.384)
    assert account.get_view().dividends.conversions == ()
    account.settle_dividends("2022-07-05")
    assert account.get_view().dividends.conversions == (hidden,)


def test_conversion_day_lots_rescale_without_phantom_acquisition() -> None:
    """Lots keep their real acquisition dates; only quantity scales (#762 F2)."""
    account = Account(cash=CashBook(10_000, 10_000, 0), conversions=(_conversion(),))
    trade(account, "2022-07-04", OrderSide.BUY, 100, 2.384)
    account.settle_dividends("2022-07-05")
    account.apply_share_conversions("2022-07-05")
    account.mark_to_market({_IID: 0.596})
    account.close_dividend_day("2022-07-05")
    # Lots are book-internal lineage (the PIT view only exposes lots for
    # instruments with visible distributions), so assert on the book itself.
    book = account._dividends
    position = account.get_view().positions[_IID]
    assert position.quantity == 400
    assert [(lot.acquired, lot.quantity) for lot in book.lots] == [
        (date(2022, 7, 4), 400)
    ]
    assert sum(lot.quantity for lot in book.lots) == position.quantity


def test_merge_declarations_restores_pit_filtered_book() -> None:
    """Resume must re-union declarations the checkpoint view dropped (#762 F1)."""
    conversion = _conversion()
    account = Account(cash=CashBook(10_000, 10_000, 0), conversions=(conversion,))
    trade(account, "2022-06-28", OrderSide.BUY, 100, 2.4)
    # Checkpoint book on/before the announcement day: the PIT view dropped
    # the conversion, but runtime state (lots, entries, clock) is live.
    filtered = account.get_view().dividends
    assert conversion not in filtered.conversions
    restored = filtered.merge_declarations((), conversions=(conversion,))
    assert restored.conversions == (conversion,)
    assert restored.lots == filtered.lots
    assert restored.entries == filtered.entries
    assert restored.settled_day == filtered.settled_day
    assert restored.closed_day == filtered.closed_day
    # Conflicting re-declaration of the same identity is still rejected.
    with pytest.raises(ValueError, match="conflicting conversion revision"):
        restored.merge_declarations((), conversions=(_conversion(ratio=2.0),))
