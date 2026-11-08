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
