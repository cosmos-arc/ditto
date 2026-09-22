"""
Shared retained-price valuation machinery for historical replay queries.

Manual, Paper, and Model history all price instruments from PIT-visible
retained bars under one stale-carry policy; this module is the single
authority for that policy and its helpers.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
from decimal import Decimal
from zoneinfo import ZoneInfo

from ditto_data.query.contracts import PITQueryContext
from ditto_features.technical_analysis.contracts import TechnicalBar
from ditto_kernel.identity import InstrumentId

from ditto_application.queries.technical_analysis import (
    TechnicalAnalysisSourcePort,
)

__all__ = [
    "VALUATION_POLICY_VERSION",
    "HistoryPointView",
    "HistoryQuality",
    "HistorySegmentView",
    "PricedBar",
    "bars_by_instrument",
    "end_of_day",
    "price_at",
    "trade_day",
    "visible_bars",
]

VALUATION_POLICY_VERSION = "account-valuation-stale-evidence-v1"

_SHANGHAI = ZoneInfo("Asia/Shanghai")
_ZERO = Decimal("0")


@dataclass(frozen=True, kw_only=True)
class HistoryQuality:
    """One machine-readable quality or absence mark."""

    code: str
    detail: str = ""


@dataclass(frozen=True, kw_only=True)
class HistoryPointView:
    """One dated valuation row; missing prices leave value gaps."""

    on_date: str
    valuation_instant: str
    total_value: Decimal | None
    cash: Decimal | None
    external_flow: Decimal
    period_return: Decimal | None
    cumulative_return: Decimal | None
    segment_id: int | None
    price_time: str | None
    stale: bool
    source_snapshot_ids: tuple[str, ...]
    quality: tuple[HistoryQuality, ...]


@dataclass(frozen=True, kw_only=True)
class HistorySegmentView:
    """One continuous positive-capital run with its own linked TWR."""

    segment_id: int
    start_date: str
    end_date: str
    start_value: Decimal
    end_value: Decimal
    linked_return: Decimal | None
    closed_reason: str
    quality: tuple[HistoryQuality, ...]


@dataclass(frozen=True)
class PricedBar:
    """One retained close chosen for a valuation date."""

    instrument_id: int
    price: Decimal
    occurred_at: datetime
    source_snapshot_id: str
    price_date: str
    carried: bool


def end_of_day(day: date) -> datetime:
    """Shanghai end-of-day instant for one calendar day."""
    return datetime.combine(day, time.max, tzinfo=_SHANGHAI)


def trade_day(instant: datetime) -> date:
    """Bars carry a Shanghai-midnight occurred_at; map it to the trade date."""
    return instant.astimezone(_SHANGHAI).date()


def visible_bars(
    bars: tuple[TechnicalBar, ...],
    on_date: date,
) -> tuple[TechnicalBar, ...]:
    """Bars PIT-visible at the close of one valuation date."""
    day_end = end_of_day(on_date)
    return tuple(
        bar
        for bar in bars
        if trade_day(bar.occurred_at) <= on_date and bar.publication_at <= day_end
    )


def price_at(
    *,
    instrument_id: int,
    bars: tuple[TechnicalBar, ...],
    on_date: date,
    market_traded_on_date: bool,
) -> PricedBar | HistoryQuality:
    """
    Price one instrument on one date under the stale-carry policy.

    Failures return a ``price_missing`` quality mark with the reason in its
    detail; the carried price is only offered while trading demonstrably
    resumed after the candidate bar or the candidate row is suspended.
    """
    visible = visible_bars(bars, on_date)
    if not visible:
        return HistoryQuality(code="price_missing", detail=str(instrument_id))
    latest = max(visible, key=lambda bar: bar.occurred_at)
    price = Decimal(str(latest.close))
    if not price.is_finite() or price <= _ZERO:
        return HistoryQuality(
            code="price_missing", detail=f"{instrument_id}:invalid_close"
        )
    candidate_day = trade_day(latest.occurred_at)
    carried = candidate_day < on_date
    if carried:
        # Carry-forward is only defensible while trading demonstrably
        # continued after the candidate bar (or the candidate itself is a
        # suspended row); an unknown delisting residual must stay a gap.
        resumed_after_candidate = any(
            trade_day(bar.occurred_at) > candidate_day for bar in bars
        )
        if not (resumed_after_candidate or latest.suspended):
            return HistoryQuality(
                code="price_missing",
                detail=(
                    f"{instrument_id}:unknown_trading_status_after_"
                    f"{candidate_day.isoformat()}"
                ),
            )
    return PricedBar(
        instrument_id=instrument_id,
        price=price,
        occurred_at=latest.occurred_at,
        source_snapshot_id=latest.source_snapshot_id,
        price_date=candidate_day.isoformat(),
        carried=carried and market_traded_on_date,
    )


def bars_by_instrument(
    source: TechnicalAnalysisSourcePort,
    context: PITQueryContext,
    instrument_ids: tuple[int, ...],
) -> dict[int, tuple[TechnicalBar, ...]]:
    """Load retained bars per instrument under one PIT context."""
    bars: dict[int, tuple[TechnicalBar, ...]] = {}
    for instrument_id in instrument_ids:
        bars[instrument_id] = source.load(
            context,
            instrument_id=InstrumentId(instrument_id),
            instrument_code=str(instrument_id),
        )
    return bars
