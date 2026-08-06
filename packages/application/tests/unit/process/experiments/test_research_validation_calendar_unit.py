"""Focused contracts for typed trading-calendar evidence construction."""

from __future__ import annotations

from datetime import date, timedelta

from ditto_application.research_validation_calendar import (
    CalendarMonth,
    TradingCalendarEvidence,
    TradingCalendarMonthClosure,
    TradingCalendarSourceIdentity,
)


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
