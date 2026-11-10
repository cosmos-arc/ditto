"""Dated ETF secondary-market rules from explicit retained declarations (#758)."""

from collections.abc import Mapping, Sequence
from datetime import date
from math import isfinite

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

from ditto_execution.reality.ordinary_equity import CashEquityListing

_CATEGORIES = {"equity", "bond", "gold", "cross_border", "money", "commodity_futures"}
_UNITS = {
    "trading_category": "text",
    "trading_currency": "text",
    "lot_size": "count",
    "tick_size": "price",
    "settlement_cycle": "days",
    "price_limit_pct": "ratio",
}


def etf_rule_history(
    listing: CashEquityListing,
    *,
    facts: Sequence[Mapping[str, object]],
    commission_rate: float,
    start: str,
    end: str,
    trading_days: list[str],
) -> tuple[_InstrumentRules, ...]:
    """Require one sourced version per field/session; no category inference."""
    if listing.asset_class != "etf" or listing.exchange not in {"SSE", "SZSE"}:
        raise ValueError(f"unsupported ETF identity: {listing.instrument_id}")
    if start > end or start < "2014-01-01":
        raise ValueError(
            "ETF history requires a period starting on or after 2014-01-01"
        )
    if not isfinite(commission_rate) or commission_rate < 0:
        raise ValueError("commission_rate must be finite and non-negative")
    if not trading_days or trading_days != sorted(set(trading_days)):
        raise ValueError("ETF rules require a sorted, unique trading calendar")
    history: list[_InstrumentRules] = []
    previous: tuple[dict[str, str], str, bool] | None = None
    days = [date.fromisoformat(day).isoformat() for day in trading_days]
    # The roster's delist_date is the request's frozen exit fact (#764): a
    # session on/after it demands no dated declarations a terminated fund no
    # longer publishes — the last pre-exit rule carries those days via the PIT
    # lookup, the participation gate keeps them out of execution, and no
    # liquidation is invented. A window with no pre-exit session keeps the
    # honest "no covered ETF trading session" refusal below.
    for day in (
        day
        for day in days
        if max(start, listing.list_date) <= day <= end
        and (listing.delist_date is None or day < listing.delist_date)
    ):
        values, effective_from = _declared_values(facts, listing.instrument_id, day)
        closing = listing.exchange == "SZSE" or day >= "2026-07-06"
        effective_from = max(
            effective_from,
            listing.list_date,
            "2026-07-06" if closing and listing.exchange == "SSE" else "2014-01-01",
        )
        if (values, effective_from, closing) == previous:
            continue
        definition = _InstrumentDefinition(
            instrument_id=listing.instrument_id,
            asset_class="etf",
            exchange={"SSE": "XSHG", "SZSE": "XSHE"}[listing.exchange],
            currency=values["trading_currency"],
            tick_size=float(values["tick_size"]),
            lot_size=int(values["lot_size"]),
            multiplier=1.0,
            board_segment=values["trading_category"] + "_etf",
            lifecycle_state="normal",
            ipo_date=listing.list_date,
            delisting_date=listing.delist_date,
        )
        if history and definition != history[0][0]:
            raise ValueError(
                f"unresolved ETF definition change: {listing.instrument_id} {day}"
            )
        history.append(
            (
                definition,
                _TradingRuleSet(
                    instrument_id=listing.instrument_id,
                    as_of_date=effective_from,
                    settlement_cycle=int(values["settlement_cycle"]),
                    fund_settlement_cycle=0,
                    price_limit_pct=float(values["price_limit_pct"]),
                    order_types_supported=("market", "limit", "market_on_close")
                    if closing
                    else ("market", "limit"),
                    call_auction_sessions=("09:15-09:25", "14:57-15:00")
                    if closing
                    else ("09:15-09:25",),
                    max_limit_order_quantity=1_000_000,
                    max_market_order_quantity=1_000_000,
                ),
                _FeeSchedule(
                    instrument_id=listing.instrument_id,
                    as_of_date=effective_from,
                    commission_rate=commission_rate,
                    min_commission=5.0,
                    stamp_duty_rate=0.0,
                    transfer_fee_rate=0.0,
                ),
            )
        )
        previous = values, effective_from, closing
    if not history:
        raise ValueError(
            f"no covered ETF trading session: {listing.instrument_id} {start}..{end}"
        )
    return tuple(history)


def _declared_values(
    facts: Sequence[Mapping[str, object]], instrument_id: int, day: str
) -> tuple[dict[str, str], str]:
    values: dict[str, str] = {}
    effective_from = "2014-01-01"
    for field, unit in _UNITS.items():
        active = [
            row
            for row in facts
            if row.get("field") == field
            and str(row["effective_from"]) <= day
            and (row.get("effective_to") is None or day < str(row["effective_to"]))
        ]
        if (
            len(active) != 1
            or active[0].get("unit") != unit
            or not active[0].get("basis")
        ):
            raise ValueError(
                f"missing/ambiguous ETF rule: {instrument_id} {day} {field}"
            )
        values[field] = str(active[0]["value"])
        effective_from = max(effective_from, str(active[0]["effective_from"]))
    try:
        for field in ("lot_size", "tick_size", "settlement_cycle", "price_limit_pct"):
            number = float(values[field])
            values[field] = str(int(number)) if number.is_integer() else str(number)
    except (ValueError, OverflowError) as error:
        raise ValueError(f"invalid ETF rule number: {instrument_id} {day}") from error
    if (
        values["trading_category"] not in _CATEGORIES
        or values["trading_currency"] != "CNY"
        or values["lot_size"] != "100"
        or values["tick_size"] != "0.001"
        or values["settlement_cycle"] not in {"0", "1"}
        or values["price_limit_pct"] not in {"0.1", "0.2"}
    ):
        raise ValueError(f"unverified ETF rule values: {instrument_id} {day}")
    return values, effective_from
