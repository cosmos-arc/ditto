"""ChiNext effective dates, identities and submission boundaries (#754)."""

from dataclasses import replace

import pytest
from ditto_execution.orders.ids import ClientOrderId
from ditto_execution.orders.model import Order
from ditto_execution.reality.order import order_rule_rejection
from ditto_execution.reality.ordinary_equity import (
    CashEquityListing,
    cash_stock_board,
    ordinary_execution_fields,
    stock_rule_history,
)
from ditto_execution.rules import InMemoryRuleProvider
from ditto_kernel.identity import InstrumentId
from ditto_kernel.order import OrderSide, OrderType

_LISTING = CashEquityListing(
    InstrumentId(1), "300750", "stock", "SZSE", "2018-06-11", None
)
_DAYS = [
    "2020-08-13",
    "2020-08-14",
    "2020-08-17",
    "2020-08-18",
    "2020-08-19",
    "2020-08-20",
    "2020-08-21",
    "2020-08-24",
    "2020-08-25",
    "2020-08-26",
]


def _provider(
    listing: CashEquityListing = _LISTING, end: str = _DAYS[-1]
) -> InMemoryRuleProvider:
    history = stock_rule_history(
        listing,
        commission_rate=0.0003,
        start="2020-08-20",
        end=end,
        trading_days=[day for day in _DAYS if day <= end],
    )
    return InMemoryRuleProvider(
        definitions={listing.instrument_id: history[0][0]},
        trading_rules={listing.instrument_id: [row[1] for row in history]},
        fee_schedules={listing.instrument_id: [row[2] for row in history]},
    )


def test_code_range_excludes_cdr_index_wrong_exchange_and_unicode() -> None:
    for ticker in ("300000", "300750", "301001", "302132", "309799"):
        assert cash_stock_board("stock", "SZSE", ticker) == "chinext"
    for asset, exchange, ticker in [
        ("stock", "SZSE", "309800"),
        ("stock", "SZSE", "309999"),
        ("stock", "SZSE", "30000"),
        ("stock", "SZSE", "\uff13\uff10\uff10\uff17\uff15\uff10"),
        ("stock", "SSE", "300750"),
        ("index", "SZSE", "300015"),
    ]:
        assert cash_stock_board(asset, exchange, ticker) is None


@pytest.mark.pit
def test_reform_does_not_rewrite_prior_bands_fees_or_transition_exceptions() -> None:
    provider = _provider()
    before = provider.get_rules("2020-08-21", [InstrumentId(1)])[InstrumentId(1)]
    after = provider.get_rules("2020-08-24", [InstrumentId(1)])[InstrumentId(1)]
    assert (
        before
        == _provider(end="2020-08-21").get_rules("2020-08-21", [InstrumentId(1)])[
            InstrumentId(1)
        ]
    )
    assert (before[1].price_limit_pct, after[1].price_limit_pct) == (0.1, 0.2)
    assert before[2] == after[2]
    assert after[0].board_segment == "chinext"
    for rules, upper, lower in [(before, 11.0, 9.0), (after, 12.0, 8.0)]:
        row = {
            "trade_date": rules[1].as_of_date,
            "is_st": False,
            "pre_close": 10.0,
            "limit_up": upper,
            "limit_down": lower,
        }
        assert ordinary_execution_fields(row, rules, start_date="2014-01-01") == {}
        with pytest.raises(ValueError, match="disagrees with dated rule"):
            ordinary_execution_fields(
                {**row, "limit_up": 11.0 if upper == 12.0 else 12.0},
                rules,
                start_date="2014-01-01",
            )
        for unknown in (None, True):
            with pytest.raises(ValueError, match="risk-warning"):
                ordinary_execution_fields(
                    {**row, "is_st": unknown}, rules, start_date="2014-01-01"
                )
    for ticker in ("300090", "300156", "300216"):
        rule = _provider(replace(_LISTING, ticker=ticker)).get_trading_rule(
            InstrumentId(1), "2020-08-24"
        )
        assert rule is not None
        assert rule.price_limit_pct == 0.1
        assert rule.max_limit_order_quantity == 1_000_000


@pytest.mark.parametrize(
    ("kind", "maximum"),
    [
        (OrderType.MARKET, 150_000),
        (OrderType.LIMIT, 300_000),
        (OrderType.MARKET_ON_CLOSE, 300_000),
    ],
)
def test_submission_cap_applies_before_partial_fill_and_only_after_reform(
    kind: OrderType, maximum: int
) -> None:
    provider = _provider()
    before = provider.get_trading_rule(InstrumentId(1), "2020-08-21")
    after = provider.get_trading_rule(InstrumentId(1), "2020-08-24")
    assert before is not None
    assert after is not None
    order = Order(
        ClientOrderId("cap"),
        InstrumentId(1),
        kind,
        OrderSide.BUY,
        maximum,
        10.0 if kind is OrderType.LIMIT else None,
    )
    assert order_rule_rejection(order, after) is None
    oversized = order.with_quantity(maximum + 100)
    assert order_rule_rejection(oversized, before) is None
    assert (
        order_rule_rejection(oversized, after) == "order_quantity_exceeds_dated_maximum"
    )


@pytest.mark.pit
def test_pre_reform_ipo_has_one_initial_session_even_across_reform() -> None:
    listing = replace(_LISTING, list_date="2020-08-20")
    provider = _provider(listing)
    first = provider.get_rules("2020-08-20", [InstrumentId(1)])[InstrumentId(1)]
    second = provider.get_rules("2020-08-21", [InstrumentId(1)])[InstrumentId(1)]
    third = provider.get_rules("2020-08-24", [InstrumentId(1)])[InstrumentId(1)]
    assert first[1].price_limit_pct is None
    assert "market" not in first[1].order_types_supported
    assert (
        ordinary_execution_fields(
            {"trade_date": "2020-08-20", "is_st": False}, first, start_date="2020-08-20"
        )
        == {}
    )
    assert second[1].price_limit_pct == 0.1
    assert third[1].price_limit_pct == 0.2
