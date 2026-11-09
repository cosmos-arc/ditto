"""
Observed cash-equity rules for limited historical research (#723, #753).

Authority/effective dates: docs/evidence/ordinary-backtest-20261108/rules.md.
Main-board history: docs/evidence/mainboard-rules-753.md.
These are reconstructed rules, never evidence of historical knowability.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from math import isfinite

from ditto_kernel.identity import InstrumentId as _InstrumentId
from ditto_kernel.trading import (
    FeeSchedule as _FeeSchedule,
)
from ditto_kernel.trading import (
    InstrumentDefinition as _InstrumentDefinition,
)
from ditto_kernel.trading import (
    InstrumentRules as _InstrumentRules,
)
from ditto_kernel.trading import (
    TradingRuleSet as _TradingRuleSet,
)

from ditto_execution.reality.price import round_to_tick

__all__ = [
    "MIN_ORDINARY_LISTED_DAYS",
    "RULES_EFFECTIVE_FROM",
    "RULES_OBSERVED_AT",
    "CashEquityListing",
    "is_mainboard_stock",
    "mainboard_rule_history",
    "mainboard_trading_history",
    "ordinary_equity_rules",
    "ordinary_execution_fields",
]

RULES_OBSERVED_AT = "2026-11-08T06:22:22+00:00"
RULES_EFFECTIVE_FROM = "2023-08-28"
MIN_ORDINARY_LISTED_DAYS = 30
_A_SHARE_CODE_LENGTH = 6
_IPO_NO_LIMIT_SESSIONS = 5

# Only the explicitly selected, verified ordinary-research instruments. This is
# deliberately not a classifier for arbitrary ETFs, STAR/BSE stocks or IPOs.
_COVERAGE = {
    ("stock", "SZSE", "000001"): 0.10,
    ("stock", "SZSE", "000333"): 0.10,
    ("stock", "SSE", "600000"): 0.10,
    ("stock", "SSE", "600036"): 0.10,
    ("stock", "SSE", "600519"): 0.10,
    ("etf", "SZSE", "159901"): 0.10,
    ("etf", "SZSE", "159915"): 0.20,
    ("etf", "SSE", "510050"): 0.10,
    ("etf", "SSE", "510300"): 0.10,
    ("etf", "SSE", "510500"): 0.10,
}


@dataclass(frozen=True)
class CashEquityListing:
    """Registry identity/lifecycle supplied by the application boundary."""

    instrument_id: _InstrumentId
    ticker: str
    asset_class: str
    exchange: str
    list_date: str
    delist_date: str | None


def is_mainboard_stock(asset_class: str, exchange: str, ticker: str) -> bool:
    """Main-board domestic A shares; exclude B shares, STAR, ChiNext and funds."""
    return (
        asset_class == "stock"
        and len(ticker) == _A_SHARE_CODE_LENGTH
        and ticker.isascii()
        and ticker.isdigit()
        and (
            (exchange == "SSE" and ticker.startswith(("600", "601", "603", "605")))
            or (
                exchange == "SZSE"
                and "000001" <= ticker <= "004999"
                and not "001001" <= ticker <= "001199"
            )
        )
    )


def mainboard_rule_history(
    listing: CashEquityListing,
    *,
    commission_rate: float,
    start: str,
    end: str,
    trading_days: list[str],
) -> tuple[_InstrumentRules, ...]:
    """Bind IPO phases to verified sessions, retaining the existing fee boundary."""
    if not is_mainboard_stock(listing.asset_class, listing.exchange, listing.ticker):
        raise ValueError(f"not a covered main-board A share: {listing.instrument_id}")
    if start < RULES_EFFECTIVE_FROM:
        raise ValueError(
            "historical stock fee schedule missing before 2023-08-28 (#757); "
            + f"requested {listing.instrument_id} {start}..{end}"
        )
    base = ordinary_equity_rules(
        listing,
        commission_rate=commission_rate,
        start=start,
        end=end,
        historical_reconstruction=True,
    )
    return tuple(
        (base[0], rule, base[2])
        for rule in mainboard_trading_history(
            listing, start=start, end=end, trading_days=trading_days
        )
    )


def mainboard_trading_history(
    listing: CashEquityListing, *, start: str, end: str, trading_days: list[str]
) -> tuple[_TradingRuleSet, ...]:
    """Dated main-board trading rules; fee coverage is a separate requirement."""
    if not is_mainboard_stock(listing.asset_class, listing.exchange, listing.ticker):
        raise ValueError(f"not a covered main-board A share: {listing.instrument_id}")
    if not "2014-01-01" <= start <= end <= RULES_OBSERVED_AT[:10]:
        raise ValueError(
            "main-board trading rules cover 2014-01-01 through the observed date"
        )
    _validate_mainboard_calendar(listing, start, trading_days)
    versions: dict[str, float | None] = {
        "2014-01-01": 0.1,
        "2014-06-13": 0.1,
        "2023-04-10": 0.1,
        "2026-07-06": 0.1,
    }
    if listing.exchange == "SSE":
        versions["2018-08-20"] = 0.1
    if listing.list_date >= trading_days[0]:
        sessions = [day for day in trading_days if day >= listing.list_date]
        initial_sessions = (
            _IPO_NO_LIMIT_SESSIONS if listing.list_date >= "2023-04-10" else 1
        )
        versions[listing.list_date] = None
        for effective in list(versions):
            if (
                listing.list_date < effective
                and sum(day < effective for day in sessions) < initial_sessions
            ):
                versions[effective] = None
        if len(sessions) > initial_sessions:
            versions[sessions[initial_sessions]] = 0.1
    history: list[_TradingRuleSet] = []
    for effective, band in sorted(versions.items()):
        if effective > end:
            continue
        closing_auction = listing.exchange == "SZSE" or effective >= "2018-08-20"
        history.append(
            _TradingRuleSet(
                instrument_id=listing.instrument_id,
                as_of_date=effective,
                settlement_cycle=1,
                fund_settlement_cycle=0,
                price_limit_pct=band,
                order_types_supported=_mainboard_order_types(
                    listing.exchange, band, closing_auction
                ),
                call_auction_sessions=("09:15-09:25", "14:57-15:00")
                if closing_auction
                else ("09:15-09:25",),
            )
        )
    return tuple(history)


def _mainboard_order_types(
    exchange: str, band: float | None, closing_auction: bool
) -> tuple[str, ...]:
    """SZSE market orders require a band; close orders use the auction model."""
    order_types = ["limit"]
    if band is not None or exchange == "SSE":
        order_types.insert(0, "market")
    if closing_auction:
        order_types.append("market_on_close")
    return tuple(order_types)


def _validate_mainboard_calendar(
    listing: CashEquityListing, start: str, trading_days: list[str]
) -> None:
    if not trading_days or trading_days != sorted(set(trading_days)):
        raise ValueError("main-board rules require a sorted, unique trading calendar")
    for day in trading_days:
        date.fromisoformat(day)
    if listing.list_date >= trading_days[0] and listing.list_date not in trading_days:
        raise ValueError(
            f"listing date is not a verified trading session: {listing.instrument_id}"
        )
    if (
        listing.list_date < trading_days[0]
        and sum(day < start for day in trading_days) < _IPO_NO_LIMIT_SESSIONS
    ):
        raise ValueError("main-board calendar must retain five prior trading sessions")


def ordinary_equity_rules(
    listing: CashEquityListing,
    *,
    commission_rate: float,
    start: str,
    end: str,
    historical_reconstruction: bool = False,
) -> _InstrumentRules:
    """Reject unknown coverage/exit periods; retain seed commission assumptions."""
    key = (listing.asset_class, listing.exchange, listing.ticker)
    mainboard = historical_reconstruction and is_mainboard_stock(*key)
    if key not in _COVERAGE and not mainboard:
        raise ValueError(f"missing ordinary asset rule: {listing.instrument_id} {key}")
    representative_2014 = (
        historical_reconstruction
        and key
        in {
            ("etf", "SSE", "510050"),
            ("etf", "SSE", "510300"),
            ("etf", "SSE", "510500"),
        }
        and "2014-09-26" <= start <= end <= "2014-12-31"
    )
    effective_from = "2014-09-26" if representative_2014 else RULES_EFFECTIVE_FROM
    if (
        not representative_2014
        and not RULES_EFFECTIVE_FROM <= start <= end <= RULES_OBSERVED_AT[:10]
    ):
        raise ValueError(
            "ordinary rule coverage is "
            + f"{RULES_EFFECTIVE_FROM}..{RULES_OBSERVED_AT[:10]}"
        )
    if (
        not mainboard
        and (date.fromisoformat(start) - date.fromisoformat(listing.list_date)).days
        < MIN_ORDINARY_LISTED_DAYS
    ) or (listing.delist_date is not None and listing.delist_date <= end):
        raise ValueError(
            "unresolved listing/exit valuation for "
            + f"{listing.instrument_id}; refuse liquidation or dropping held positions"
        )
    if not isfinite(commission_rate) or commission_rate < 0:
        raise ValueError("commission_rate must be finite and non-negative")
    stock = listing.asset_class == "stock"
    iid = listing.instrument_id
    return (
        _InstrumentDefinition(
            instrument_id=iid,
            asset_class=listing.asset_class,
            exchange={"SSE": "XSHG", "SZSE": "XSHE"}[listing.exchange],
            currency="CNY",
            tick_size=0.01 if stock else 0.001,
            lot_size=100,
            multiplier=1.0,
            board_segment="main" if stock else "domestic_equity_etf",
            lifecycle_state="normal",
            ipo_date=listing.list_date,
            delisting_date=listing.delist_date,
        ),
        _TradingRuleSet(
            instrument_id=iid,
            as_of_date=effective_from,
            settlement_cycle=1,
            fund_settlement_cycle=0,
            price_limit_pct=0.10 if mainboard else _COVERAGE[key],
            order_types_supported=("market", "limit", "market_on_close"),
            call_auction_sessions=("09:15-09:25",)
            if representative_2014
            else ("09:15-09:25", "14:57-15:00"),
        ),
        _FeeSchedule(
            instrument_id=iid,
            as_of_date=effective_from,
            commission_rate=commission_rate,
            min_commission=5.0,
            stamp_duty_rate=0.0005 if stock else 0.0,
            transfer_fee_rate=0.00001 if stock else 0.0,
        ),
    )


def ordinary_execution_fields(
    row: Mapping[str, object], rules: _InstrumentRules, *, start_date: str
) -> dict[str, float | bool | None]:
    """Validate daily execution state and derive verified ETF price bands."""
    definition, rule, _ = rules
    iid, day = definition.instrument_id, str(row["trade_date"])
    if (
        day >= start_date
        and row.get("_previous_adj") is not None
        and (row.get("adj_factor") != row["_previous_adj"])
    ):
        raise ValueError(
            f"corporate action requires cash/share accounting: {iid} {day}"
        )
    if definition.asset_class == "stock":
        return _stock_execution_fields(row, rules)
    # Recorded turnover proves trading occurred; missing quotes cannot prove a halt.
    volume, previous = row.get("volume"), row.get("pre_close")
    if not isinstance(volume, (int, float)) or not isfinite(volume) or volume <= 0:
        raise ValueError(f"unknown ETF suspension/valuation: {iid} {day}")
    if (
        not isinstance(previous, (int, float))
        or not isfinite(previous)
        or previous <= 0
        or rule.price_limit_pct is None
    ):
        raise ValueError(f"missing ETF limit inputs: {iid} {day}")
    previous_decimal = Decimal(str(previous))
    band = Decimal(str(rule.price_limit_pct))
    return {
        "limit_up": round_to_tick(previous_decimal * (1 + band), definition.tick_size),
        "limit_down": round_to_tick(
            previous_decimal * (1 - band), definition.tick_size
        ),
        "is_suspended": False,
    }


def _stock_execution_fields(
    row: Mapping[str, object], rules: _InstrumentRules
) -> dict[str, float | bool | None]:
    definition, rule, _ = rules
    iid, day = definition.instrument_id, str(row["trade_date"])
    if row.get("is_st") is not False:
        raise ValueError(f"unverified risk-warning rule/status: {iid} {day}")
    if rule.price_limit_pct is None and (definition.ipo_date or "") >= "2023-04-10":
        # The verified listing calendar/rule proves the exemption. A missing
        # or extreme vendor price must never independently grant this state.
        return {"limit_up": None, "limit_down": None}
    if rule.price_limit_pct is None:
        return {}  # Legacy IPO first-day asymmetric provider bands remain required.
    previous = row.get("pre_close")
    if (
        not isinstance(previous, (int, float))
        or not isfinite(previous)
        or previous <= 0
    ):
        raise ValueError(f"missing stock previous close: {iid} {day}")
    for name, direction in (("limit_up", 1), ("limit_down", -1)):
        band = Decimal(str(rule.price_limit_pct))
        expected = round_to_tick(
            Decimal(str(previous)) * (1 + direction * band), definition.tick_size
        )
        if expected == previous:
            expected = round_to_tick(
                Decimal(str(previous)) + direction * Decimal(str(definition.tick_size)),
                definition.tick_size,
            )
        expected = max(definition.tick_size, expected)
        if row.get(name) != expected:
            raise ValueError(
                f"stock price band disagrees with dated rule: {iid} {day} {name}"
            )
    return {}
