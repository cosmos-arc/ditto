"""
Shared retained-price valuation machinery for historical replay queries.

Manual, Paper, and Model history all price instruments from PIT-visible
retained bars under one stale-carry policy and render one point/segment
view shape; this module is the single authority for those helpers.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime, time
from decimal import Decimal
from zoneinfo import ZoneInfo

from ditto_data.query.contracts import PITQueryContext
from ditto_features.technical_analysis.contracts import TechnicalBar
from ditto_kernel.identity import InstrumentId
from ditto_portfolio.account_returns import ReturnSeries

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
    "build_history_points",
    "build_history_segments",
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


def build_history_points(
    *,
    series: ReturnSeries,
    valuation_dates: list[date],
    priced_dates: Mapping[str, tuple[PricedBar, ...]],
    display_cash: Mapping[str, Decimal],
    gap_quality: Mapping[str, tuple[HistoryQuality, ...]],
    flows_by_date: Mapping[str, Decimal],
) -> tuple[HistoryPointView, ...]:
    """Render dated rows: gap days keep reasons, stale prices are marked."""
    by_date = {point.on_date: point for point in series.points}
    points: list[HistoryPointView] = []
    for day in valuation_dates:
        key = day.isoformat()
        priced = priced_dates.get(key, ())
        stale = any(bar.carried for bar in priced)
        calculator_point = by_date.get(key)
        quality: tuple[HistoryQuality, ...] = (
            tuple(gap_quality.get(key, ()))
            if calculator_point is None
            else tuple(
                HistoryQuality(code=reason.code.value, detail=reason.detail)
                for reason in calculator_point.reasons
            )
        )
        if calculator_point is None:
            total_value = None
            period_return = None
            cumulative_return = None
            segment_id = None
        else:
            total_value = calculator_point.total_value
            period_return = calculator_point.period_return
            cumulative_return = calculator_point.cumulative_return
            segment_id = calculator_point.segment_id
        if stale:
            stale_marks = tuple(
                HistoryQuality(
                    code="stale_price",
                    detail=f"{bar.instrument_id}:{bar.price_date}",
                )
                for bar in priced
                if bar.carried
            )
            quality = (*quality, *stale_marks)
        points.append(
            HistoryPointView(
                on_date=key,
                valuation_instant=end_of_day(day).isoformat(),
                total_value=total_value,
                cash=display_cash.get(key),
                external_flow=flows_by_date.get(key, _ZERO),
                period_return=period_return,
                cumulative_return=cumulative_return,
                segment_id=segment_id,
                price_time=(
                    max(bar.occurred_at for bar in priced).isoformat()
                    if priced
                    else None
                ),
                stale=stale,
                source_snapshot_ids=tuple(
                    sorted({bar.source_snapshot_id for bar in priced})
                ),
                quality=quality,
            )
        )
    return tuple(points)


def build_history_segments(series: ReturnSeries) -> tuple[HistorySegmentView, ...]:
    """Map calculator segments to their view shape with reason codes."""
    return tuple(
        HistorySegmentView(
            segment_id=segment.segment_id,
            start_date=segment.start_date,
            end_date=segment.end_date,
            start_value=segment.start_value,
            end_value=segment.end_value,
            linked_return=segment.linked_return,
            closed_reason=segment.closed_reason,
            quality=tuple(
                HistoryQuality(code=reason.code.value, detail=reason.detail)
                for reason in segment.reasons
            ),
        )
        for segment in series.segments
    )
