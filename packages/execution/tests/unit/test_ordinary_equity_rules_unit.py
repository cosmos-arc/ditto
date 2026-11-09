"""Ordinary research rules cover only explicitly verified cash equities."""

from dataclasses import replace

import pytest
from ditto_execution.reality.ordinary_equity import (
    CashEquityListing,
    ordinary_equity_rules,
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
