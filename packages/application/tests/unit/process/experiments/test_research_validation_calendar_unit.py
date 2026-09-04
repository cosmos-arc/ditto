"""Focused contracts for typed trading-calendar evidence construction."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import date, datetime, timedelta
from typing import cast

import pytest
from ditto_application.exceptions import AppProcessError
from ditto_application.research_validation_calendar import (
    CalendarMonth,
    TradingCalendarDay,
    TradingCalendarDayStatus,
    TradingCalendarEvidence,
    TradingCalendarMonthClosure,
    TradingCalendarSourceIdentity,
    complete_months,
    seal_trading_calendar,
    sessions_by_month,
)

pytestmark = pytest.mark.pit


def _weekday_sessions(month: CalendarMonth) -> tuple[date, ...]:
    current = date(month.year, month.month, 1)
    stop = date(month.next().year, month.next().month, 1)
    sessions: list[date] = []
    while current < stop:
        if current.weekday() < 5:
            sessions.append(current)
        current += timedelta(days=1)
    return tuple(sessions)


def test_typed_source_preserves_calendar_evidence_payload_identity() -> None:
    """Grouping source facts must not change the persisted canonical hash."""
    month = CalendarMonth(2026, 1)
    closure = TradingCalendarMonthClosure.create(
        month=month,
        open_sessions=_weekday_sessions(month),
    )
    source = TradingCalendarSourceIdentity(
        dataset_id="trade_cal",
        snapshot_id="calendar-provider",
        manifest_hash="c" * 64,
        certified_through=date(2026, 1, 31),
        authority_as_of=date(2026, 2, 1),
    )

    evidence = TradingCalendarEvidence.create(
        calendar_id="sse-szse-a-share",
        version=1,
        source=source,
        month_closures=(closure,),
    )

    assert (
        evidence.dataset_id,
        evidence.snapshot_id,
        evidence.manifest_hash,
        evidence.certified_through,
        evidence.authority_as_of,
    ) == (
        source.dataset_id,
        source.snapshot_id,
        source.manifest_hash,
        source.certified_through,
        source.authority_as_of,
    )
    assert evidence.payload_hash == (
        "c0247268983dc2b02bc67b0fdb9a1725ab2b599b2b15fc6cd309df97485bd4f0"
    )


def _closure(month: CalendarMonth | None = None) -> TradingCalendarMonthClosure:
    effective_month = month or CalendarMonth(2026, 1)
    return TradingCalendarMonthClosure.create(
        month=effective_month,
        open_sessions=_weekday_sessions(effective_month),
    )


def _source(*, through: date = date(2026, 1, 31)) -> TradingCalendarSourceIdentity:
    return TradingCalendarSourceIdentity(
        dataset_id="trade_cal",
        snapshot_id="calendar-provider",
        manifest_hash="c" * 64,
        certified_through=through,
        authority_as_of=through + timedelta(days=1),
    )


def _evidence() -> TradingCalendarEvidence:
    return TradingCalendarEvidence.create(
        calendar_id="sse-szse-a-share",
        version=1,
        source=_source(),
        month_closures=(_closure(),),
    )


def _expect_spec_invalid(reason: str, factory: Callable[[], object]) -> None:
    with pytest.raises(AppProcessError) as exc_info:
        factory()
    assert exc_info.value.details["code"] == "SPEC_INVALID"
    assert exc_info.value.details["reason"] == reason


@pytest.mark.parametrize(
    ("year", "month", "reason"),
    [
        (True, 1, "invalid_calendar_month_year"),
        (0, 1, "invalid_calendar_month_year"),
        (2026, 0, "invalid_calendar_month_number"),
        (2026, 13, "invalid_calendar_month_number"),
    ],
)
def test_calendar_month_rejects_ambiguous_ranges(
    year: int,
    month: int,
    reason: str,
) -> None:
    _expect_spec_invalid(reason, lambda: CalendarMonth(year, month))

    with pytest.raises(AppProcessError) as exc_info:
        CalendarMonth.from_date(cast("date", datetime(2026, 1, 1)))
    assert exc_info.value.details["reason"] == "invalid_calendar_month_date"


def test_calendar_month_next_handles_year_boundary() -> None:
    assert CalendarMonth(2026, 12).next() == CalendarMonth(2027, 1)


def test_calendar_day_requires_exact_date_and_status_types() -> None:
    _expect_spec_invalid(
        "invalid_trading_calendar_date",
        lambda: TradingCalendarDay(
            cast("date", datetime(2026, 1, 2)),
            TradingCalendarDayStatus.OPEN,
        ),
    )
    _expect_spec_invalid(
        "invalid_trading_calendar_day_status",
        lambda: TradingCalendarDay(
            date(2026, 1, 2),
            cast("TradingCalendarDayStatus", "open"),
        ),
    )


def test_month_closure_requires_exact_ordered_sessions_inside_its_month() -> None:
    month = CalendarMonth(2026, 1)
    for sessions, reason in (
        (cast("tuple[date, ...]", []), "trading_sessions_must_be_non_empty_tuple"),
        ((), "trading_sessions_must_be_non_empty_tuple"),
        (
            (date(2026, 1, 2), cast("date", "2026-01-05")),
            "invalid_trading_session",
        ),
        (
            (date(2026, 1, 2), date(2026, 1, 2)),
            "trading_sessions_not_strictly_increasing",
        ),
        (
            _weekday_sessions(CalendarMonth(2026, 2)),
            "trading_calendar_session_outside_month",
        ),
    ):
        _expect_spec_invalid(
            reason,
            lambda sessions=sessions: TradingCalendarMonthClosure.create(
                month=month,
                open_sessions=sessions,
            ),
        )


def test_month_closure_revalidation_rejects_forged_graph_and_hashes() -> None:
    closure = _closure()
    _expect_spec_invalid(
        "invalid_trading_calendar_closure_month",
        lambda: replace(closure, month=cast("CalendarMonth", object())),
    )
    forged_month = CalendarMonth(2026, 1)
    object.__setattr__(forged_month, "month", 13)
    _expect_spec_invalid(
        "invalid_calendar_month_number",
        lambda: replace(closure, month=forged_month),
    )
    _expect_spec_invalid(
        "trading_calendar_days_must_be_tuple",
        lambda: replace(
            closure,
            days=cast("tuple[TradingCalendarDay, ...]", [*closure.days]),
        ),
    )
    _expect_spec_invalid(
        "invalid_trading_calendar_day",
        lambda: replace(
            closure,
            days=cast("tuple[TradingCalendarDay, ...]", (object(),)),
        ),
    )

    forged_day = closure.days[0]
    object.__setattr__(forged_day, "calendar_date", datetime(2026, 1, 1))
    _expect_spec_invalid(
        "invalid_trading_calendar_date",
        lambda: replace(closure, days=(forged_day, *closure.days[1:])),
    )

    closure = _closure()
    forged_day = closure.days[0]
    object.__setattr__(forged_day, "status", "closed")
    _expect_spec_invalid(
        "invalid_trading_calendar_day_status",
        lambda: replace(closure, days=(forged_day, *closure.days[1:])),
    )

    closure = _closure()
    _expect_spec_invalid(
        "trading_calendar_month_not_fully_closed",
        lambda: replace(closure, days=closure.days[:-1]),
    )

    saturday = next(
        index
        for index, item in enumerate(closure.days)
        if item.calendar_date.weekday() >= 5
    )
    weekend_open = replace(
        closure.days[saturday],
        status=TradingCalendarDayStatus.OPEN,
    )
    _expect_spec_invalid(
        "a_share_weekend_cannot_be_open",
        lambda: replace(
            closure,
            days=(
                *closure.days[:saturday],
                weekend_open,
                *closure.days[saturday + 1 :],
            ),
        ),
    )
    _expect_spec_invalid(
        "invalid_trading_calendar_month_hash",
        lambda: replace(closure, content_hash="not-a-hash"),
    )
    _expect_spec_invalid(
        "trading_calendar_month_hash_mismatch",
        lambda: replace(closure, content_hash="0" * 64),
    )


def test_calendar_source_rejects_untyped_or_inverted_authority() -> None:
    _expect_spec_invalid(
        "invalid_trading_calendar_source_identity",
        lambda: replace(_source(), dataset_id=""),
    )
    _expect_spec_invalid(
        "invalid_trading_calendar_source_identity",
        lambda: replace(_source(), manifest_hash="not-a-hash"),
    )
    _expect_spec_invalid(
        "invalid_trading_calendar_certification_range",
        lambda: replace(_source(), certified_through=cast("date", "2026-01-31")),
    )
    _expect_spec_invalid(
        "trading_calendar_exceeds_certified_authority_range",
        lambda: replace(
            _source(),
            certified_through=date(2026, 2, 2),
            authority_as_of=date(2026, 2, 1),
        ),
    )


def test_calendar_factory_requires_exact_source_and_closure_collections() -> None:
    _expect_spec_invalid(
        "invalid_trading_calendar_source_identity",
        lambda: TradingCalendarEvidence.create(
            calendar_id="sse-szse-a-share",
            version=1,
            source=cast("TradingCalendarSourceIdentity", object()),
            month_closures=(_closure(),),
        ),
    )
    _expect_spec_invalid(
        "trading_calendar_closures_must_be_tuple",
        lambda: TradingCalendarEvidence.create(
            calendar_id="sse-szse-a-share",
            version=1,
            source=_source(),
            month_closures=cast(
                "tuple[TradingCalendarMonthClosure, ...]", [_closure()]
            ),
        ),
    )


def test_calendar_evidence_revalidates_identity_range_sequence_and_hash() -> None:
    evidence = _evidence()
    _expect_spec_invalid(
        "invalid_trading_calendar_id",
        lambda: replace(evidence, calendar_id=""),
    )
    _expect_spec_invalid(
        "invalid_trading_calendar_source_identity",
        lambda: replace(evidence, snapshot_id=""),
    )
    _expect_spec_invalid(
        "invalid_trading_calendar_certification_range",
        lambda: replace(
            evidence,
            authority_as_of=cast("date", "2026-02-01"),
        ),
    )
    _expect_spec_invalid(
        "invalid_trading_calendar_version",
        lambda: replace(evidence, version=cast("int", True)),
    )
    _expect_spec_invalid(
        "trading_calendar_closures_must_be_non_empty_tuple",
        lambda: replace(evidence, month_closures=()),
    )
    _expect_spec_invalid(
        "invalid_trading_calendar_month_closure",
        lambda: replace(
            evidence,
            month_closures=cast("tuple[TradingCalendarMonthClosure, ...]", (object(),)),
        ),
    )
    _expect_spec_invalid(
        "trading_calendar_closures_must_be_non_empty_tuple",
        lambda: replace(
            evidence,
            month_closures=cast(
                "tuple[TradingCalendarMonthClosure, ...]", [_closure()]
            ),
        ),
    )

    march = _closure(CalendarMonth(2026, 3))
    _expect_spec_invalid(
        "trading_calendar_months_not_contiguous",
        lambda: replace(evidence, month_closures=(_closure(), march)),
    )
    _expect_spec_invalid(
        "trading_calendar_exceeds_certified_authority_range",
        lambda: replace(
            evidence,
            certified_through=date(2026, 1, 30),
            authority_as_of=date(2026, 1, 30),
        ),
    )
    _expect_spec_invalid(
        "invalid_trading_calendar_payload_hash",
        lambda: replace(evidence, payload_hash="not-a-hash"),
    )
    _expect_spec_invalid(
        "trading_calendar_payload_hash_mismatch",
        lambda: replace(evidence, payload_hash="0" * 64),
    )


def test_calendar_seal_rejects_forged_nested_graph_before_copy() -> None:
    _expect_spec_invalid(
        "invalid_trading_calendar_evidence",
        lambda: seal_trading_calendar(object()),
    )

    evidence = _evidence()
    object.__setattr__(evidence, "month_closures", [*evidence.month_closures])
    _expect_spec_invalid(
        "trading_calendar_closures_must_be_tuple",
        lambda: seal_trading_calendar(evidence),
    )

    evidence = _evidence()
    object.__setattr__(evidence, "month_closures", (object(),))
    _expect_spec_invalid(
        "invalid_trading_calendar_month_closure",
        lambda: seal_trading_calendar(evidence),
    )

    evidence = _evidence()
    closure = evidence.month_closures[0]
    object.__setattr__(closure, "month", object())
    _expect_spec_invalid(
        "invalid_trading_calendar_month_closure",
        lambda: seal_trading_calendar(evidence),
    )

    evidence = _evidence()
    closure = evidence.month_closures[0]
    object.__setattr__(closure, "days", (object(),))
    _expect_spec_invalid(
        "invalid_trading_calendar_day",
        lambda: seal_trading_calendar(evidence),
    )


def test_calendar_seal_returns_an_equal_independent_value_graph() -> None:
    evidence = _evidence()

    sealed = seal_trading_calendar(evidence)

    assert sealed == evidence
    assert sealed is not evidence
    assert sealed.month_closures[0] is not evidence.month_closures[0]
    assert sealed.month_closures[0].days[0] is not evidence.month_closures[0].days[0]


def test_session_month_helpers_fail_closed_on_gaps_and_future_sessions() -> None:
    january = CalendarMonth(2026, 1)
    february = CalendarMonth(2026, 2)
    march = CalendarMonth(2026, 3)
    _expect_spec_invalid(
        "trading_session_after_last_complete_month",
        lambda: sessions_by_month((date(2026, 3, 2),), february),
    )
    _expect_spec_invalid(
        "last_complete_month_has_no_sessions",
        lambda: sessions_by_month((date(2026, 1, 2),), february),
    )
    _expect_spec_invalid(
        "calendar_month_missing",
        lambda: complete_months(
            session_months={
                january: (date(2026, 1, 2),),
                march: (date(2026, 3, 2),),
            },
            strategy_eligible_start=date(2026, 1, 2),
            last_complete_month=march,
        ),
    )
    assert (
        complete_months(
            session_months={january: (date(2026, 1, 2),)},
            strategy_eligible_start=date(2026, 2, 2),
            last_complete_month=january,
        )
        == ()
    )
