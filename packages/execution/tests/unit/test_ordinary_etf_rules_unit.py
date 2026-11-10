"""ETF history consumes dated declarations, never inferred categories."""

from dataclasses import replace

import pytest
from ditto_execution.reality.ordinary_equity import (
    CashEquityListing,
    ordinary_execution_fields,
)
from ditto_execution.reality.ordinary_etf import etf_rule_history
from ditto_kernel.identity import InstrumentId


def _facts(category="cross_border", cycle="1", band="0.1"):
    return [
        {
            "field": field,
            "value": value,
            "unit": unit,
            "effective_from": "2014-01-01",
            "effective_to": "2026-11-10",
            "basis": "synthetic dated exchange declaration",
        }
        for field, value, unit in [
            ("trading_category", category, "text"),
            ("trading_currency", "CNY", "text"),
            ("lot_size", "100", "count"),
            ("tick_size", "0.001", "price"),
            ("settlement_cycle", cycle, "days"),
            ("price_limit_pct", band, "ratio"),
        ]
    ]


def _listing(exchange="SSE"):
    return CashEquityListing(
        InstrumentId(2_000_001), "510900", "etf", exchange, "2012-10-22", None
    )


def _history(facts, days, listing=None):
    return etf_rule_history(
        listing or _listing(),
        facts=facts,
        commission_rate=0.0003,
        start=days[0],
        end=days[-1],
        trading_days=days,
    )


@pytest.mark.pit
def test_cross_border_t0_switch_and_future_rule_do_not_backfill():
    facts = _facts()
    cycle = next(row for row in facts if row["field"] == "settlement_cycle")
    cycle["effective_to"] = "2015-01-19"
    facts += [
        {
            **cycle,
            "value": "0",
            "effective_from": "2015-01-19",
            "effective_to": "2027-01-01",
        },
        {**cycle, "value": "1", "effective_from": "2027-01-01", "effective_to": None},
    ]
    history = _history(facts, ["2015-01-16", "2015-01-19"])
    assert [(row[1].as_of_date, row[1].settlement_cycle) for row in history] == [
        ("2014-01-01", 1),
        ("2015-01-19", 0),
    ]
    later = _history(facts, ["2020-08-21"])[0]
    assert later[1].as_of_date == later[2].as_of_date == "2015-01-19"
    assert all(row[0].board_segment == "cross_border_etf" for row in history)


@pytest.mark.parametrize(
    ("category", "cycle"),
    [
        ("equity", "1"),
        ("bond", "0"),
        ("gold", "0"),
        ("cross_border", "0"),
        ("money", "0"),
        ("commodity_futures", "0"),
    ],
)
def test_six_declared_categories_use_share_quotes_and_secondary_market_rules(
    category, cycle
):
    definition, rule, fee = _history(_facts(category, cycle), ["2020-08-21"])[0]
    assert (
        definition.currency,
        definition.lot_size,
        definition.tick_size,
        definition.multiplier,
    ) == ("CNY", 100, 0.001, 1.0)
    assert rule.settlement_cycle == int(cycle)
    assert (rule.max_limit_order_quantity, rule.max_market_order_quantity) == (
        1_000_000,
        1_000_000,
    )
    assert (
        fee.commission_rate,
        fee.min_commission,
        fee.stamp_duty_rate,
        fee.transfer_fee_rate,
    ) == (0.0003, 5.0, 0.0, 0.0)


@pytest.mark.pit
def test_chinext_band_switch_uses_membership_declaration_not_the_code():
    facts = _facts("equity")
    band = next(row for row in facts if row["field"] == "price_limit_pct")
    band["effective_to"] = "2020-08-24"
    facts.append(
        {
            **band,
            "value": "0.2",
            "effective_from": "2020-08-24",
            "effective_to": "2026-11-10",
        }
    )
    history = _history(
        facts, ["2020-08-21", "2020-08-24"], replace(_listing("SZSE"), ticker="159915")
    )
    assert [row[1].price_limit_pct for row in history] == [0.1, 0.2]
    assert all("market_on_close" in row[1].order_types_supported for row in history)


def test_sse_etf_close_auction_begins_in_2026_not_the_2018_stock_change():
    history = _history(_facts(), ["2018-08-20", "2026-07-03", "2026-07-06"])
    assert [row[1].as_of_date for row in history] == ["2014-01-01", "2026-07-06"]
    assert history[0][1].call_auction_sessions == ("09:15-09:25",)
    assert "market_on_close" not in history[0][1].order_types_supported
    assert history[-1][1].call_auction_sessions == ("09:15-09:25", "14:57-15:00")


@pytest.mark.parametrize(
    "problem",
    ["missing", "gap", "overlap", "invalid_category", "invalid_unit", "expiry"],
)
def test_incomplete_or_ambiguous_rules_refuse_with_exact_instrument_and_date(problem):
    facts = _facts()
    if problem == "missing":
        facts = [row for row in facts if row["field"] != "trading_category"]
    elif problem == "gap":
        facts[0]["effective_from"] = "2014-01-03"
    elif problem == "overlap":
        facts.append(dict(facts[0]))
    elif problem == "invalid_category":
        facts[0]["value"] = "today_inferred_category"
    elif problem == "invalid_unit":
        facts[2]["unit"] = "lots"
    else:
        facts[0]["effective_to"] = "2014-01-02"
    with pytest.raises(ValueError, match=r"2000001.*2014-01-02"):
        _history(facts, ["2014-01-02"])


def test_verified_etf_listing_does_not_wait_thirty_calendar_days():
    listing = replace(_listing("SZSE"), ticker="159985", list_date="2019-12-05")
    history = _history(_facts("commodity_futures", "0"), ["2019-12-05"], listing)
    assert history[0][0].ipo_date == "2019-12-05"
    # A termination on the only session day leaves no covered session: the
    # refusal is honest about coverage, no trading rule is invented.
    with pytest.raises(ValueError, match="no covered ETF trading session"):
        _history(_facts(), ["2019-12-05"], replace(listing, delist_date="2019-12-05"))


def test_frozen_exit_fact_inside_window_keeps_rules_and_stops_declarations():
    """A frozen ETF termination keeps rules; post-exit sessions demand nothing.

    Mirrors #763's stock stance: the roster's delist_date is the request's
    frozen exit fact. Sessions on/after it carry the last pre-exit rule via
    the PIT lookup instead of demanding dated declarations a terminated fund
    no longer publishes.
    """
    listing = replace(_listing(), delist_date="2014-01-16")
    history = _history(_facts(), ["2014-01-15", "2014-01-16", "2014-01-17"], listing)
    assert [row[1].as_of_date for row in history] == ["2014-01-01"]
    assert history[0][0].delisting_date == "2014-01-16"


def test_exit_fact_after_the_window_changes_nothing():
    listing = replace(_listing(), delist_date="2014-02-01")
    history = _history(_facts(), ["2014-01-15", "2014-01-16"], listing)
    assert [row[1].as_of_date for row in history] == ["2014-01-01"]


def test_etf_cash_reconciles_source_factor_and_ex_price_without_accepting_folds():
    rules = _history(_facts(category="equity"), ["2025-06-18"])[0]
    row = {
        "trade_date": "2025-06-18",
        "_previous_close": 3.989,
        "_previous_adj": 1.2078,
        "adj_factor": 1.235,
        "pre_close": 3.901,
        "volume": 100.0,
    }
    assert ordinary_execution_fields(
        row, rules, start_date="2025-06-18", cash_dividend=0.088
    ) == {"limit_up": 4.291, "limit_down": 3.511, "is_suspended": False}
    for changed, cash, shares in [
        ({}, None, 0),
        ({"adj_factor": 2.47}, 0.088, 0),
        ({"adj_factor": 1.2355}, 0.088, 0),
        ({"pre_close": 3.989}, 0.088, 0),
        ({}, 0.088, 1),
    ]:
        with pytest.raises(ValueError, match=r"corporate action|ETF ex reference"):
            ordinary_execution_fields(
                {**row, **changed},
                rules,
                start_date="2025-06-18",
                cash_dividend=cash,
                share_ratio=shares,
            )


def _conversion_row(**overrides: object) -> dict[str, object]:
    """159941.SZ 2022-07-05 1:4 split session as retained by the production store."""
    row: dict[str, object] = {
        "trade_date": "2022-07-05",
        "_previous_close": 2.384,
        "_previous_adj": 1.0,
        "adj_factor": 4.0,
        "pre_close": 0.596,
        "volume": 5_390_000.0,
    }
    row.update(overrides)
    return row


def test_declared_conversion_reconciles_factor_jump_and_reference_price():
    rules = _history(_facts("equity"), ["2022-07-05"])[0]
    assert ordinary_execution_fields(
        _conversion_row(), rules, start_date="2022-07-05", conversion_ratio=4.0
    ) == {"limit_up": 0.656, "limit_down": 0.536, "is_suspended": False}
    # A factor quantum of provider rounding stays explained at source precision.
    assert (
        ordinary_execution_fields(
            _conversion_row(adj_factor=3.9999),
            rules,
            start_date="2022-07-05",
            conversion_ratio=4.0,
        )["limit_up"]
        == 0.656
    )
    # No declared event, or the wrong one: the jump stays unexplained.
    for kwargs, changed in [
        ({}, {}),
        ({"conversion_ratio": 2.0}, {}),
        ({"conversion_ratio": 4.0}, {"adj_factor": 3.999}),
        ({"conversion_ratio": 4.0}, {"adj_factor": 2.0}),
    ]:
        with pytest.raises(ValueError, match=r"corporate action|conversion"):
            ordinary_execution_fields(
                _conversion_row(**changed),
                rules,
                start_date="2022-07-05",
                **kwargs,
            )
    # The published ex-rights reference must equal the rounded split price.
    for changed in ({"pre_close": 0.5}, {"pre_close": 2.384}, {"pre_close": 0.597}):
        with pytest.raises(ValueError, match="unverified ETF conversion reference"):
            ordinary_execution_fields(
                _conversion_row(**changed),
                rules,
                start_date="2022-07-05",
                conversion_ratio=4.0,
            )


def test_zero_volume_published_row_valuates_without_trading():
    rules = _history(_facts("equity"), ["2022-07-06"])[0]
    halted = {
        "trade_date": "2022-07-06",
        "pre_close": 0.596,
        "close": 0.596,
        "volume": 0.0,
    }
    # An exchange-published zero-turnover row carries its own close and
    # reference; orders reject on zero volume instead of failing the run.
    assert ordinary_execution_fields(halted, rules, start_date="2022-07-06") == {
        "limit_up": None,
        "limit_down": None,
        "is_suspended": False,
    }
    with pytest.raises(ValueError, match="unknown ETF suspension/valuation"):
        ordinary_execution_fields(
            {**halted, "volume": -1.0}, rules, start_date="2022-07-06"
        )
    with pytest.raises(ValueError, match="unknown ETF suspension/valuation"):
        ordinary_execution_fields(
            {**halted, "volume": None}, rules, start_date="2022-07-06"
        )
    with pytest.raises(ValueError, match="missing ETF limit inputs"):
        ordinary_execution_fields(
            {**halted, "pre_close": 0.0}, rules, start_date="2022-07-06"
        )


def test_same_day_conversion_and_cash_distribution_aborts_honestly():
    """No verifier models the combined jump; this pin documents the refusal."""
    rules = _history(_facts("equity"), ["2022-07-05"])[0]
    # 2.384 close − 0.02 cash per share, then 1:4: neither single-event
    # verifier can explain the compound reference/factor move together.
    row = _conversion_row(pre_close=0.591)
    with pytest.raises(ValueError, match=r"corporate action|unverified"):
        ordinary_execution_fields(
            row,
            rules,
            start_date="2022-07-05",
            cash_dividend=0.02,
            conversion_ratio=4.0,
        )
