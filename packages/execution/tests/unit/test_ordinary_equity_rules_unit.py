"""Ordinary research rules cover only explicitly verified cash equities."""

from dataclasses import replace

import pytest
from ditto_execution.reality.ordinary_equity import (
    CashEquityListing,
    is_mainboard_stock,
    mainboard_rule_history,
    mainboard_trading_history,
    ordinary_equity_rules,
    ordinary_execution_fields,
)
from ditto_kernel.identity import InstrumentId


def test_verified_stock_and_etf_have_distinct_rules_and_fees() -> None:
    stock = CashEquityListing(
        InstrumentId(1_000_001), "000001", "stock", "SZSE", "1991-04-03", None
    )
    definition, rule, fee = ordinary_equity_rules(
        stock, commission_rate=0.001, start="2026-10-08", end="2026-11-06"
    )
    assert (definition.tick_size, definition.lot_size, rule.settlement_cycle) == (
        0.01,
        100,
        1,
    )
    assert (fee.commission_rate, fee.stamp_duty_rate, fee.transfer_fee_rate) == (
        0.001,
        0.0005,
        0.00001,
    )
    etf = CashEquityListing(
        InstrumentId(2_001_567), "159915", "etf", "SZSE", "2011-12-09", None
    )
    definition, rule, fee = ordinary_equity_rules(
        etf, commission_rate=0.0003, start="2026-10-08", end="2026-11-06"
    )
    assert (definition.tick_size, rule.settlement_cycle, rule.price_limit_pct) == (
        0.001,
        1,
        0.2,
    )
    assert (fee.stamp_duty_rate, fee.transfer_fee_rate) == (0, 0)
    for invalid in [
        replace(stock, ticker="999999"),
        replace(stock, delist_date="2026-10-19"),
    ]:
        with pytest.raises(ValueError):
            ordinary_equity_rules(
                invalid, commission_rate=0.001, start="2026-10-08", end="2026-11-06"
            )


def test_historical_opt_in_has_a_verified_2014_etf_window_only() -> None:
    listing = CashEquityListing(
        InstrumentId(2_000_001), "510300", "etf", "SSE", "2012-05-28", None
    )
    _, rule, fee = ordinary_equity_rules(
        listing,
        commission_rate=0.0003,
        start="2014-10-13",
        end="2014-11-07",
        historical_reconstruction=True,
    )
    assert (rule.as_of_date, rule.price_limit_pct, rule.settlement_cycle) == (
        "2014-09-26",
        0.1,
        1,
    )
    assert rule.call_auction_sessions == ("09:15-09:25",)
    assert (fee.stamp_duty_rate, fee.transfer_fee_rate) == (0.0, 0.0)
    for start, end, enabled in [
        ("2014-10-13", "2014-11-07", False),
        ("2014-01-01", "2014-11-07", True),
        ("2014-10-13", "2026-11-07", True),
    ]:
        with pytest.raises(ValueError, match="coverage"):
            ordinary_equity_rules(
                listing,
                commission_rate=0.0003,
                start=start,
                end=end,
                historical_reconstruction=enabled,
            )


@pytest.mark.pit
def test_mainboard_ipo_rules_change_on_sixth_session_not_calendar_age() -> None:
    listing = CashEquityListing(
        InstrumentId(1_005_567), "001246", "stock", "SZSE", "2026-09-30", None
    )
    # National Day closure: the sixth session is fourteen calendar days later.
    days = [
        "2026-09-30",
        "2026-10-08",
        "2026-10-09",
        "2026-10-12",
        "2026-10-13",
        "2026-10-14",
    ]
    history = mainboard_rule_history(
        listing, commission_rate=0.001, start=days[0], end=days[-1], trading_days=days
    )
    from ditto_execution.rules import InMemoryRuleProvider

    provider = InMemoryRuleProvider(
        definitions={listing.instrument_id: history[0][0]},
        trading_rules={listing.instrument_id: [row[1] for row in history]},
        fee_schedules={listing.instrument_id: [row[2] for row in history]},
    )
    fifth = provider.get_rules("2026-10-13", [listing.instrument_id])[
        listing.instrument_id
    ]
    sixth = provider.get_rules("2026-10-14", [listing.instrument_id])[
        listing.instrument_id
    ]
    assert fifth[1].price_limit_pct is None
    assert sixth[1].price_limit_pct == 0.1
    assert fifth[1].as_of_date == "2026-09-30"
    assert sixth[1].as_of_date == "2026-10-14"
    assert (sixth[0].lot_size, sixth[0].tick_size, sixth[1].settlement_cycle) == (
        100,
        0.01,
        1,
    )


def test_mainboard_identity_calendar_and_older_fee_boundaries() -> None:
    assert is_mainboard_stock("stock", "SZSE", "003999")
    for ticker in ("001001", "001199", "300001", "000000", "\uff10" * 5 + "\uff11"):
        assert not is_mainboard_stock("stock", "SZSE", ticker)
    assert not is_mainboard_stock("stock", "SSE", "688001")
    listing = CashEquityListing(
        InstrumentId(1), "600000", "stock", "SSE", "1999-11-10", None
    )
    days = [
        "2018-08-10",
        "2018-08-13",
        "2018-08-14",
        "2018-08-15",
        "2018-08-16",
        "2018-08-17",
        "2018-08-20",
    ]
    history = mainboard_trading_history(
        listing, start=days[-2], end=days[-1], trading_days=days
    )
    before = [rule for rule in history if rule.as_of_date <= days[-2]][-1]
    after = history[-1]
    assert "market_on_close" not in before.order_types_supported
    assert "market_on_close" in after.order_types_supported
    with pytest.raises(ValueError, match="five prior trading sessions"):
        mainboard_trading_history(
            listing, start=days[-2], end=days[-1], trading_days=days[-2:]
        )
    with pytest.raises(ValueError, match="fee schedule missing"):
        mainboard_rule_history(
            listing,
            commission_rate=0.001,
            start=days[-2],
            end=days[-1],
            trading_days=days,
        )


def test_stock_band_has_at_least_one_tick_difference() -> None:
    listing = CashEquityListing(
        InstrumentId(1), "000001", "stock", "SZSE", "1991-04-03", None
    )
    rules = ordinary_equity_rules(
        listing, commission_rate=0.001, start="2026-10-08", end="2026-10-08"
    )
    row = {
        "trade_date": "2026-10-08",
        "is_st": False,
        "pre_close": 0.04,
        "limit_up": 0.05,
        "limit_down": 0.03,
    }
    assert ordinary_execution_fields(row, rules, start_date="2026-10-08") == {}
    with pytest.raises(ValueError, match="disagrees"):
        ordinary_execution_fields(
            {**row, "limit_up": 0.04}, rules, start_date="2026-10-08"
        )
