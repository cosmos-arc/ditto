"""
Finite, observed cash-equity rules for limited historical research (#723).

Authority/effective dates: docs/evidence/ordinary-backtest-20261108/rules.md.
These are reconstructed rules, never evidence of historical knowability.
"""

from dataclasses import dataclass
from datetime import date
from math import isfinite

from ditto_kernel.identity import InstrumentId
from ditto_kernel.trading import (
    FeeSchedule,
    InstrumentDefinition,
    InstrumentRules,
    TradingRuleSet,
)

RULES_OBSERVED_AT = "2026-11-08T06:22:22+00:00"
RULES_EFFECTIVE_FROM = "2023-08-28"
_MIN_LISTED_CALENDAR_DAYS = 30

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

    instrument_id: InstrumentId
    ticker: str
    asset_class: str
    exchange: str
    list_date: str
    delist_date: str | None


def ordinary_equity_rules(
    listing: CashEquityListing, *, commission_rate: float, start: str, end: str
) -> InstrumentRules:
    """Reject unknown coverage/exit periods; retain seed commission assumptions."""
    key = (listing.asset_class, listing.exchange, listing.ticker)
    if key not in _COVERAGE:
        raise ValueError(f"missing ordinary asset rule: {listing.instrument_id} {key}")
    if not RULES_EFFECTIVE_FROM <= start <= end <= RULES_OBSERVED_AT[:10]:
        raise ValueError(
            "ordinary rule coverage is "
            + f"{RULES_EFFECTIVE_FROM}..{RULES_OBSERVED_AT[:10]}"
        )
    if (
        date.fromisoformat(start) - date.fromisoformat(listing.list_date)
    ).days < _MIN_LISTED_CALENDAR_DAYS or (
        listing.delist_date is not None and listing.delist_date <= end
    ):
        raise ValueError(
            "unresolved listing/exit valuation for "
            + f"{listing.instrument_id}; refuse liquidation or dropping held positions"
        )
    if not isfinite(commission_rate) or commission_rate < 0:
        raise ValueError("commission_rate must be finite and non-negative")
    stock = listing.asset_class == "stock"
    iid = listing.instrument_id
    return (
        InstrumentDefinition(
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
        TradingRuleSet(
            instrument_id=iid,
            as_of_date=RULES_EFFECTIVE_FROM,
            settlement_cycle=1,
            fund_settlement_cycle=0,
            price_limit_pct=_COVERAGE[key],
            order_types_supported=("market", "limit", "market_on_close"),
            call_auction_sessions=("09:15-09:25", "14:57-15:00"),
        ),
        FeeSchedule(
            instrument_id=iid,
            as_of_date="2023-08-28",
            commission_rate=commission_rate,
            min_commission=5.0,
            stamp_duty_rate=0.0005 if stock else 0.0,
            transfer_fee_rate=0.00001 if stock else 0.0,
        ),
    )
