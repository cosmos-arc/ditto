"""
Observed cash-equity rules for limited historical research (#723, #753–#755).

Authority/effective dates: docs/evidence/ordinary-backtest-20261108/rules.md.
Stock history: docs/evidence/{mainboard-rules-753,chinext-rules-754,star-rules-755}.md.
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
    "cash_stock_board",
    "is_mainboard_stock",
    "ordinary_equity_rules",
    "ordinary_execution_fields",
    "stock_rule_history",
    "stock_trading_history",
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


def cash_stock_board(asset_class: str, exchange: str, ticker: str) -> str | None:
    """Verified domestic stock code ranges; exclude CDRs and index identities."""
    if is_mainboard_stock(asset_class, exchange, ticker):
        return "main"
    if (
        asset_class == "stock"
        and exchange == "SZSE"
        and len(ticker) == _A_SHARE_CODE_LENGTH
        and ticker.isascii()
        and ticker.isdigit()
        and "300000" <= ticker <= "309799"
    ):
        return "chinext"
    if (
        asset_class == "stock"
        and exchange == "SSE"
        and len(ticker) == _A_SHARE_CODE_LENGTH
        and ticker.isascii()
        and ticker.isdigit()
        and ticker.startswith("688")
    ):
        return "star"
    return None


def stock_rule_history(
    listing: CashEquityListing,
    *,
    commission_rate: float,
    start: str,
    end: str,
    trading_days: list[str],
) -> tuple[_InstrumentRules, ...]:
    """Bind independent trading and fee effective dates to the same consumer."""
    if cash_stock_board(listing.asset_class, listing.exchange, listing.ticker) is None:
        raise ValueError(f"not a covered domestic A share: {listing.instrument_id}")
    base = ordinary_equity_rules(
        listing,
        commission_rate=commission_rate,
        start=start,
        end=end,
        historical_reconstruction=True,
    )
    trading = stock_trading_history(
        listing, start=start, end=end, trading_days=trading_days
    )
    fees = _stock_fee_history(listing, commission_rate=commission_rate)
    dates = sorted({row.as_of_date for row in (*trading, *fees)})
    return tuple(
        (
            base[0],
            max(
                (row for row in trading if row.as_of_date <= day),
                key=lambda row: row.as_of_date,
            ),
            max(
                (row for row in fees if row.as_of_date <= day),
                key=lambda row: row.as_of_date,
            ),
        )
        for day in dates
        if trading[0].as_of_date <= day <= end
    )


def _stock_fee_history(
    listing: CashEquityListing, *, commission_rate: float
) -> tuple[_FeeSchedule, ...]:
    """CSDC charges excluding broker retention; assumptions in #757 evidence."""
    # Issuer statements establish these non-CNY-1 denominations for 2014–2015.
    nominal = {"601899": 0.1, "603993": 0.2}.get(listing.ticker, 1.0)
    early_shanghai = listing.exchange == "SSE"
    return tuple(
        _FeeSchedule(
            instrument_id=listing.instrument_id,
            as_of_date=day,
            commission_rate=commission_rate,
            min_commission=5.0,
            stamp_duty_rate=stamp,
            transfer_fee_rate=transfer,
            transfer_fee_per_share=per_share,
        )
        for day, stamp, transfer, per_share in [
            (
                "2014-01-01",
                0.001,
                0.0 if early_shanghai else 0.0000255,
                nominal * 0.0003 if early_shanghai else 0.0,
            ),
            ("2015-08-01", 0.001, 0.00002, 0.0),
            ("2022-04-29", 0.001, 0.00001, 0.0),
            ("2023-08-28", 0.0005, 0.00001, 0.0),
        ]
    )


def stock_trading_history(
    listing: CashEquityListing, *, start: str, end: str, trading_days: list[str]
) -> tuple[_TradingRuleSet, ...]:
    """Dated domestic stock trading rules; fee coverage is a separate requirement."""
    if cash_stock_board(listing.asset_class, listing.exchange, listing.ticker) is None:
        raise ValueError(f"not a covered domestic A share: {listing.instrument_id}")
    if not "2014-01-01" <= start <= end <= RULES_OBSERVED_AT[:10]:
        raise ValueError(
            "stock trading rules cover 2014-01-01 through the observed date"
        )
    _validate_stock_calendar(listing, start, trading_days)
    board = cash_stock_board(listing.asset_class, listing.exchange, listing.ticker)
    chinext, star = board == "chinext", board == "star"
    if star and (listing.list_date < "2019-07-22" or end < listing.list_date):
        raise ValueError("STAR history requires a listing on or after 2019-07-22")
    # These three already-delisting stocks retained the old mechanism throughout.
    legacy_exit = chinext and listing.ticker in {"300090", "300156", "300216"}
    registration = _registration_date(board)
    versions: dict[str, float | None] = {
        "2014-01-01": 0.1,
        "2014-06-13": 0.1,
        "2023-04-10": 0.1,
        "2026-07-06": 0.1,
    }
    if chinext and not legacy_exit:
        versions.update({"2020-08-24": 0.2, "2023-04-10": 0.2, "2026-07-06": 0.2})
    if listing.exchange == "SSE":
        versions["2018-08-20"] = 0.1
    if star:
        versions = {"2019-07-22": 0.2, "2023-04-10": 0.2, "2026-07-06": 0.2}
    _apply_ipo_exemption(versions, listing, trading_days)
    history: list[_TradingRuleSet] = []
    for effective, band in sorted(
        (day, band) for day, band in versions.items() if day <= end
    ):
        closing_auction = listing.exchange == "SZSE" or effective >= "2018-08-20"
        reformed_chinext = chinext and not legacy_exit and effective >= registration
        history.append(
            _TradingRuleSet(
                instrument_id=listing.instrument_id,
                as_of_date=effective,
                settlement_cycle=1,
                fund_settlement_cycle=0,
                price_limit_pct=band,
                order_types_supported=_stock_order_types(
                    listing.exchange, effective, band, closing_auction, star=star
                ),
                min_order_quantity=200 if star else 1,
                max_limit_order_quantity=100_000
                if star
                else (300_000 if reformed_chinext else 1_000_000),
                max_market_order_quantity=50_000
                if star
                else (150_000 if reformed_chinext else 1_000_000),
                call_auction_sessions=("09:15-09:25", "14:57-15:00")
                if closing_auction
                else ("09:15-09:25",),
            )
        )
    return tuple(history)


def _apply_ipo_exemption(
    versions: dict[str, float | None],
    listing: CashEquityListing,
    trading_days: list[str],
) -> None:
    if listing.list_date < trading_days[0]:
        return
    sessions = [day for day in trading_days if day >= listing.list_date]
    registration = _registration_date(
        cash_stock_board(listing.asset_class, listing.exchange, listing.ticker)
    )
    initial_sessions = (
        _IPO_NO_LIMIT_SESSIONS if listing.list_date >= registration else 1
    )
    if len(sessions) > initial_sessions:
        first_banded = sessions[initial_sessions]
        versions[first_banded] = max(
            ((day, band) for day, band in versions.items() if day <= first_banded),
            key=lambda item: item[0],
        )[1]
    versions[listing.list_date] = None
    for effective in list(versions):
        if (
            listing.list_date < effective
            and sum(day < effective for day in sessions) < initial_sessions
        ):
            versions[effective] = None


def _stock_order_types(
    exchange: str,
    effective: str,
    band: float | None,
    closing_auction: bool,
    *,
    star: bool,
) -> tuple[str, ...]:
    """STAR and SSE registration-era rules allow market orders without a daily band."""
    order_types = ["limit"]
    if band is not None or star or (exchange == "SSE" and effective >= "2023-04-10"):
        order_types.insert(0, "market")
    if closing_auction:
        order_types.append("market_on_close")
    return tuple(order_types)


def _validate_stock_calendar(
    listing: CashEquityListing, start: str, trading_days: list[str]
) -> None:
    if not trading_days or trading_days != sorted(set(trading_days)):
        raise ValueError("stock rules require a sorted, unique trading calendar")
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
        raise ValueError("stock calendar must retain five prior trading sessions")


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
    board = cash_stock_board(*key)
    historical_stock = historical_reconstruction and board is not None
    if key not in _COVERAGE and not historical_stock:
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
    effective_from = (
        "2014-01-01"
        if historical_stock
        else ("2014-09-26" if representative_2014 else RULES_EFFECTIVE_FROM)
    )
    if not effective_from <= start <= end <= RULES_OBSERVED_AT[:10]:
        raise ValueError(
            "ordinary rule coverage is " + f"{effective_from}..{RULES_OBSERVED_AT[:10]}"
        )
    if (
        not historical_stock
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
            lot_size=1 if board == "star" else 100,
            multiplier=1.0,
            board_segment=(board or "main") if stock else "domestic_equity_etf",
            lifecycle_state="normal",
            ipo_date=listing.list_date,
            delisting_date=listing.delist_date,
        ),
        _TradingRuleSet(
            instrument_id=iid,
            as_of_date=effective_from,
            settlement_cycle=1,
            fund_settlement_cycle=0,
            price_limit_pct=0.10 if historical_stock else _COVERAGE[key],
            order_types_supported=("market", "limit", "market_on_close"),
            call_auction_sessions=("09:15-09:25",)
            if representative_2014
            else ("09:15-09:25", "14:57-15:00"),
        ),
        max(
            (
                fee
                for fee in _stock_fee_history(listing, commission_rate=commission_rate)
                if fee.as_of_date <= start
            ),
            key=lambda fee: fee.as_of_date,
        )
        if stock
        else _FeeSchedule(
            instrument_id=iid,
            as_of_date=effective_from,
            commission_rate=commission_rate,
            min_commission=5.0,
            stamp_duty_rate=0.0,
            transfer_fee_rate=0.0,
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
    registration = _registration_date(definition.board_segment)
    if rule.price_limit_pct is None and (definition.ipo_date or "") >= registration:
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


def _registration_date(board: str | None) -> str:
    return {"star": "2019-07-22", "chinext": "2020-08-24"}.get(
        board or "", "2023-04-10"
    )
