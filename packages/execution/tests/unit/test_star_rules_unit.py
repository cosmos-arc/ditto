"""STAR dated history and explicit domestic stock identity (#755)."""

from dataclasses import replace

import pytest
from ditto_execution.reality.ordinary_equity import (
    CashEquityListing,
    cash_stock_board,
    stock_rule_history,
)
from ditto_execution.rules import InMemoryRuleProvider
from ditto_kernel.identity import InstrumentId

_LISTING = CashEquityListing(
    InstrumentId(1), "688001", "stock", "SSE", "2019-07-22", None
)
_DAYS = [
    "2019-07-22",
    "2019-07-23",
    "2019-07-24",
    "2019-07-25",
    "2019-07-26",
    "2019-07-29",
]


def test_star_identity_excludes_cdrs_and_pre_board_listings() -> None:
    assert cash_stock_board("stock", "SSE", "688001") == "star"
    for asset, exchange, ticker in [
        ("stock", "SSE", "689009"),
        ("index", "SSE", "688001"),
        ("stock", "SZSE", "688001"),
        ("stock", "SSE", "\uff16\uff18\uff18\uff10\uff10\uff11"),
    ]:
        assert cash_stock_board(asset, exchange, ticker) is None
    with pytest.raises(ValueError, match="listing on or after 2019-07-22"):
        stock_rule_history(
            replace(_LISTING, list_date="2014-01-01"),
            commission_rate=0.001,
            start="2014-01-01",
            end=_DAYS[-1],
            trading_days=["2014-01-01", *_DAYS],
        )


@pytest.mark.pit
def test_star_has_no_pre_board_rules_and_sixth_session_does_not_leak_into_fifth() -> (
    None
):
    def provider(days: list[str]) -> InMemoryRuleProvider:
        history = stock_rule_history(
            _LISTING,
            commission_rate=0.001,
            start=_DAYS[0],
            end=days[-1],
            trading_days=days,
        )
        return InMemoryRuleProvider(
            definitions={InstrumentId(1): history[0][0]},
            trading_rules={InstrumentId(1): [row[1] for row in history]},
            fee_schedules={InstrumentId(1): [row[2] for row in history]},
        )

    full = provider(_DAYS)
    assert full.get_rules("2014-01-01", [InstrumentId(1)]) == {}
    assert full.get_rules("2019-07-19", [InstrumentId(1)]) == {}
    fifth = full.get_rules(_DAYS[4], [InstrumentId(1)])[InstrumentId(1)]
    assert (
        fifth
        == provider(_DAYS[:5]).get_rules(_DAYS[4], [InstrumentId(1)])[InstrumentId(1)]
    )
    sixth = full.get_rules(_DAYS[5], [InstrumentId(1)])[InstrumentId(1)]
    assert fifth[0].board_segment == "star"
    assert fifth[0].lot_size == 1
    assert fifth[1].min_order_quantity == 200
    assert fifth[1].max_limit_order_quantity == 100_000
    assert fifth[1].max_market_order_quantity == 50_000
    assert fifth[1].price_limit_pct is None
    assert "market" in fifth[1].order_types_supported
    assert sixth[1].price_limit_pct == 0.2
    assert fifth[2] == sixth[2]
    assert sixth[2].transfer_fee_rate == 0.00002
