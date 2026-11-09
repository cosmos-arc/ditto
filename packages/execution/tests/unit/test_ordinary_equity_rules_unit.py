"""Ordinary research rules cover only explicitly verified cash equities."""

from dataclasses import replace

import pytest
from ditto_execution.reality.ordinary_equity import (
    CashEquityListing,
    is_mainboard_stock,
    ordinary_equity_rules,
    ordinary_execution_fields,
    stock_rule_history,
    stock_trading_history,
)
from ditto_kernel.identity import InstrumentId


def test_cash_event_reconciles_rounded_ex_reference_and_rejects_other_actions():
    rules = ordinary_equity_rules(
        CashEquityListing(
            InstrumentId(1), "000001", "stock", "SZSE", "1991-04-03", None
        ),
        commission_rate=0.0003,
        start="2023-06-12",
        end="2023-06-20",
        historical_reconstruction=True,
    )
    row = {
        "trade_date": "2023-06-14",
        "_previous_close": 11.77,
        "_previous_adj": 113.936,
        "adj_factor": 116.713,
        "pre_close": 11.49,
        "is_st": False,
        "is_suspended": False,
        "limit_up": 12.64,
        "limit_down": 10.34,
    }
    assert (
        ordinary_execution_fields(
            row, rules, start_date="2023-06-12", cash_dividend=0.285
        )
        == {}
    )
    for factor in (113.936, 233.426):
        with pytest.raises(ValueError, match="corporate action"):
            ordinary_execution_fields(
                {**row, "adj_factor": factor},
                rules,
                start_date="2023-06-12",
                cash_dividend=0.285,
            )
    with pytest.raises(ValueError, match="corporate action"):
        ordinary_execution_fields(row, rules, start_date="2023-06-12")


def test_pre_2014_ipo_calendar_keeps_supported_rules_without_extending_coverage() -> (
    None
):
    history = stock_rule_history(
        CashEquityListing(
            InstrumentId(1), "002703", "stock", "SZSE", "2012-11-02", None
        ),
        commission_rate=0.001,
        start="2014-01-02",
        end="2014-01-02",
        trading_days=["2012-11-02", "2012-11-05", "2012-11-06", "2014-01-02"],
    )
    assert [(rule.as_of_date, rule.price_limit_pct) for _, rule, _ in history] == [
        ("2014-01-01", 0.1)
    ]


@pytest.mark.pit
@pytest.mark.parametrize(
    ("ticker", "exchange", "day", "buy_fee", "sell_fee"),
    [
        ("600000", "SSE", "2014-01-02", 5.03, 6.03),
        ("000001", "SZSE", "2014-01-02", 5.0255, 6.0255),
        ("601899", "SSE", "2015-07-31", 5.003, 6.003),
        ("603993", "SSE", "2015-07-31", 5.006, 6.006),
        ("600000", "SSE", "2015-07-31", 5.03, 6.03),
        ("000001", "SZSE", "2015-07-31", 5.0255, 6.0255),
        ("600000", "SSE", "2015-08-03", 5.02, 6.02),
        ("000001", "SZSE", "2022-04-28", 5.02, 6.02),
        ("600000", "SSE", "2022-04-29", 5.01, 6.01),
        ("000001", "SZSE", "2023-08-25", 5.01, 6.01),
        ("600000", "SSE", "2023-08-28", 5.01, 5.51),
    ],
)
def test_historical_fee_bill_uses_fill_date_and_nominal_not_market_value(
    ticker: str, exchange: str, day: str, buy_fee: float, sell_fee: float
) -> None:
    """100 shares at CNY 10; research commission excludes CSDC transfer charges."""
    from ditto_execution.orders.ids import ClientOrderId
    from ditto_execution.orders.model import Order
    from ditto_execution.reality.fee import AShareFeeModel
    from ditto_execution.rules import InMemoryRuleProvider
    from ditto_kernel.order import OrderSide, OrderType

    listing = CashEquityListing(
        InstrumentId(1), ticker, "stock", exchange, "2012-10-09", None
    )
    history = stock_rule_history(
        listing,
        commission_rate=0.0003,
        start="2014-01-02",
        end="2026-11-06",
        trading_days=[
            "2013-12-24",
            "2013-12-25",
            "2013-12-26",
            "2013-12-27",
            "2013-12-30",
            "2014-01-02",
        ],
    )
    provider = InMemoryRuleProvider(
        definitions={listing.instrument_id: history[0][0]},
        trading_rules={listing.instrument_id: [row[1] for row in history]},
        fee_schedules={listing.instrument_id: [row[2] for row in history]},
    )
    schedule = provider.get_fee_schedule(listing.instrument_id, day)
    assert schedule is not None
    model = AShareFeeModel()
    for direction, expected in [(OrderSide.BUY, buy_fee), (OrderSide.SELL, sell_fee)]:
        order = Order(
            ClientOrderId("fee"),
            listing.instrument_id,
            OrderType.MARKET,
            direction,
            100,
            None,
        )
        assert model.calculate(order, 10.0, 100, schedule) == pytest.approx(expected)
        assert model.estimate(order, 10.0, schedule) == pytest.approx(expected)


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


def test_historical_etfs_require_retained_declarations_even_for_legacy_whitelist() -> (
    None
):
    listing = CashEquityListing(
        InstrumentId(2_000_001), "510300", "etf", "SSE", "2012-05-28", None
    )
    for start, end in [("2014-10-13", "2014-11-07"), ("2026-10-08", "2026-11-06")]:
        with pytest.raises(ValueError, match="retained dated declarations"):
            ordinary_equity_rules(
                listing,
                commission_rate=0.0003,
                start=start,
                end=end,
                historical_reconstruction=True,
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
    history = stock_rule_history(
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
    history = stock_trading_history(
        listing, start=days[-2], end=days[-1], trading_days=days
    )
    before = [rule for rule in history if rule.as_of_date <= days[-2]][-1]
    after = history[-1]
    assert "market_on_close" not in before.order_types_supported
    assert "market_on_close" in after.order_types_supported
    with pytest.raises(ValueError, match="five prior trading sessions"):
        stock_trading_history(
            listing, start=days[-2], end=days[-1], trading_days=days[-2:]
        )
    combined = stock_rule_history(
        listing, commission_rate=0.001, start=days[-2], end=days[-1], trading_days=days
    )
    assert combined[-1][2].as_of_date == "2015-08-01"


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
        "is_suspended": False,
        "pre_close": 0.04,
        "limit_up": 0.05,
        "limit_down": 0.03,
    }
    assert ordinary_execution_fields(row, rules, start_date="2026-10-08") == {}
    with pytest.raises(ValueError, match="disagrees"):
        ordinary_execution_fields(
            {**row, "limit_up": 0.04}, rules, start_date="2026-10-08"
        )


@pytest.mark.parametrize(
    ("listing_day", "market_supported"), [("2018-08-17", False), ("2023-04-10", True)]
)
def test_sse_ipo_market_order_scope_changes_with_registration_rules(
    listing_day: str, market_supported: bool
) -> None:
    listing = CashEquityListing(
        InstrumentId(1), "603001", "stock", "SSE", listing_day, None
    )
    rule = stock_trading_history(
        listing, start=listing_day, end=listing_day, trading_days=[listing_day]
    )[-1]
    assert rule.price_limit_pct is None
    assert ("market" in rule.order_types_supported) is market_supported


@pytest.mark.pit
@pytest.mark.parametrize(
    ("exchange", "ticker"), [("SSE", "600000"), ("SZSE", "000001")]
)
def test_st_rules_follow_actual_status_and_dated_market_changes(exchange, ticker):
    listing = CashEquityListing(
        InstrumentId(1), ticker, "stock", exchange, "2000-01-01", None
    )
    statuses = {
        "2014-01-02": False,
        "2014-01-03": True,
        "2014-01-06": False,
        "2021-05-14": True,
        "2021-05-17": True,
        "2026-07-03": True,
        "2026-07-06": True,
    }
    history = stock_rule_history(
        listing,
        commission_rate=0.0003,
        start="2014-01-02",
        end="2026-07-06",
        trading_days=[
            "2013-12-25",
            "2013-12-26",
            "2013-12-27",
            "2013-12-30",
            "2013-12-31",
            *statuses,
        ],
        risk_warning=statuses,
    )

    def rule_on(day):
        return max(
            (row[1] for row in history if row[1].as_of_date <= day),
            key=lambda rule: rule.as_of_date,
        )

    assert rule_on("2014-01-02").price_limit_pct == 0.1
    assert rule_on("2014-01-03").price_limit_pct == 0.05
    assert rule_on("2014-01-06").price_limit_pct == 0.1
    assert rule_on("2026-07-03").price_limit_pct == 0.05
    assert rule_on("2026-07-06").price_limit_pct == 0.1
    assert rule_on("2021-05-14").max_daily_buy_quantity == (
        500_000 if exchange == "SSE" else None
    )
    assert rule_on("2021-05-17").max_daily_buy_quantity == 500_000
    if exchange == "SSE":
        assert rule_on("2014-01-03").order_types_supported == ("limit",)
        assert "market" in rule_on("2014-01-06").order_types_supported
    rules = next(row for row in history if row[1].as_of_date == "2014-01-03")
    row = {
        "trade_date": "2014-01-03",
        "is_st": True,
        "is_suspended": False,
        "pre_close": 10.0,
        "limit_up": 10.5,
        "limit_down": 9.5,
    }
    assert ordinary_execution_fields(row, rules, start_date="2014-01-02") == {}
    with pytest.raises(ValueError, match="disagrees"):
        ordinary_execution_fields(
            {**row, "limit_up": 11.0}, rules, start_date="2014-01-02"
        )
