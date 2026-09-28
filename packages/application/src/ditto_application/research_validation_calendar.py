"""Exact, content-addressed A-share trading-calendar evidence."""

from __future__ import annotations

import hashlib
from calendar import monthrange
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from itertools import pairwise
from typing import Never, cast

import orjson

from ditto_application.exceptions import AppProcessError
from ditto_application.research_certification_contracts import (
    is_canonical_content_hash,
    is_canonical_identity,
)

__all__ = [
    "CalendarMonth",
    "TradingCalendarDay",
    "TradingCalendarDayStatus",
    "TradingCalendarEvidence",
    "TradingCalendarMonthClosure",
    "TradingCalendarSourceIdentity",
]

_MONTHS_PER_YEAR = 12
_MIN_A_SHARE_COMPLETE_MONTH_OPEN_SESSIONS = 10
_WEEKEND_START = 5


def _fail(code: str, reason: str, **details: object) -> Never:
    raise AppProcessError(
        f"validation protocol is invalid: {reason}",
        {"code": code, "reason": reason, **details},
    )


def _require_exact_int(value: object, *, field_name: str, minimum: int) -> int:
    if type(value) is not int or value < minimum:
        _fail(
            "SPEC_INVALID",
            f"invalid_{field_name}",
            field_name=field_name,
            minimum=minimum,
        )
    return value


def _payload_hash(payload: Mapping[str, object]) -> str:
    encoded = orjson.dumps(payload, option=orjson.OPT_SORT_KEYS)
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True, slots=True, order=True)
class CalendarMonth:
    """Canonical Gregorian calendar-month identity."""

    year: int
    month: int

    def __post_init__(self) -> None:
        """Reject booleans, invalid years, and invalid months."""
        _require_exact_int(self.year, field_name="calendar_month_year", minimum=1)
        month = _require_exact_int(
            self.month,
            field_name="calendar_month_number",
            minimum=1,
        )
        if month > _MONTHS_PER_YEAR:
            _fail(
                "SPEC_INVALID",
                "invalid_calendar_month_number",
                field_name="calendar_month_number",
                maximum=12,
            )

    @classmethod
    def from_date(cls, value: date) -> CalendarMonth:
        """Build a month identity from a validated exact date."""
        if type(value) is not date:
            _fail("SPEC_INVALID", "invalid_calendar_month_date")
        return cls(value.year, value.month)

    def next(self) -> CalendarMonth:
        """Return the following calendar month."""
        if self.month == _MONTHS_PER_YEAR:
            return CalendarMonth(self.year + 1, 1)
        return CalendarMonth(self.year, self.month + 1)

    def __str__(self) -> str:
        """Return the canonical YYYY-MM representation."""
        return f"{self.year:04d}-{self.month:02d}"


class TradingCalendarDayStatus(StrEnum):
    """Authoritative A-share exchange state for one Gregorian date."""

    OPEN = "open"
    CLOSED = "closed"


@dataclass(frozen=True, slots=True)
class TradingCalendarDay:
    """One exact Gregorian date in a closed trading-calendar month."""

    calendar_date: date
    status: TradingCalendarDayStatus

    def __post_init__(self) -> None:
        """Reject datetime/date subclasses and untyped exchange states."""
        if type(self.calendar_date) is not date:
            _fail("SPEC_INVALID", "invalid_trading_calendar_date")
        if type(self.status) is not TradingCalendarDayStatus:
            _fail("SPEC_INVALID", "invalid_trading_calendar_day_status")


def _month_closure_payload(
    month: CalendarMonth,
    days: tuple[TradingCalendarDay, ...],
) -> Mapping[str, object]:
    return {
        "month": str(month),
        "days": [
            {
                "date": item.calendar_date.isoformat(),
                "status": item.status.value,
            }
            for item in days
        ],
    }


@dataclass(frozen=True, slots=True)
class TradingCalendarMonthClosure:
    """Content-addressed OPEN/CLOSED evidence for every day of one month."""

    month: CalendarMonth
    days: tuple[TradingCalendarDay, ...]
    content_hash: str

    def __post_init__(self) -> None:
        """Require an exact full-month day grid and its canonical digest."""
        _validated_month_closure(self)

    @classmethod
    def create(
        cls,
        *,
        month: CalendarMonth,
        open_sessions: tuple[date, ...],
    ) -> TradingCalendarMonthClosure:
        """Build a full Gregorian closure from authoritative OPEN dates."""
        typed_month = _validated_calendar_month(
            cast("object", month),
            reason="invalid_trading_calendar_closure_month",
        )
        sessions = _validated_sessions(open_sessions)
        if any(CalendarMonth.from_date(item) != typed_month for item in sessions):
            _fail("SPEC_INVALID", "trading_calendar_session_outside_month")
        session_set = set(sessions)
        last_day = monthrange(typed_month.year, typed_month.month)[1]
        days = tuple(
            TradingCalendarDay(
                date(typed_month.year, typed_month.month, day_number),
                (
                    TradingCalendarDayStatus.OPEN
                    if date(typed_month.year, typed_month.month, day_number)
                    in session_set
                    else TradingCalendarDayStatus.CLOSED
                ),
            )
            for day_number in range(1, last_day + 1)
        )
        return cls(
            typed_month,
            days,
            _payload_hash(_month_closure_payload(typed_month, days)),
        )

    @property
    def open_sessions(self) -> tuple[date, ...]:
        """Return OPEN dates after full closure validation."""
        return tuple(
            item.calendar_date
            for item in self.days
            if item.status is TradingCalendarDayStatus.OPEN
        )


@dataclass(frozen=True, slots=True)
class TradingCalendarSourceIdentity:
    """Certified provider identity and authority range for one calendar."""

    dataset_id: str
    snapshot_id: str
    manifest_hash: str
    certified_through: date
    authority_as_of: date

    def __post_init__(self) -> None:
        """Reject untyped, non-canonical, or inverted source identities."""
        if type(self) is not TradingCalendarSourceIdentity or not all(
            is_canonical_identity(value)
            for value in (self.dataset_id, self.snapshot_id)
        ):
            _fail("SPEC_INVALID", "invalid_trading_calendar_source_identity")
        if not is_canonical_content_hash(self.manifest_hash):
            _fail("SPEC_INVALID", "invalid_trading_calendar_source_identity")
        if (
            type(self.certified_through) is not date
            or type(self.authority_as_of) is not date
        ):
            _fail("SPEC_INVALID", "invalid_trading_calendar_certification_range")
        if self.certified_through > self.authority_as_of:
            _fail("SPEC_INVALID", "trading_calendar_exceeds_certified_authority_range")


def _calendar_evidence_payload(
    *,
    calendar_id: str,
    version: int,
    source: TradingCalendarSourceIdentity,
    month_closures: tuple[TradingCalendarMonthClosure, ...],
) -> Mapping[str, object]:
    return {
        "calendar_id": calendar_id,
        "version": version,
        "source": {
            "dataset_id": source.dataset_id,
            "snapshot_id": source.snapshot_id,
            "manifest_hash": source.manifest_hash,
            "certified_through": source.certified_through.isoformat(),
            "authority_as_of": source.authority_as_of.isoformat(),
        },
        "month_closures": [
            {
                **_month_closure_payload(item.month, item.days),
                "content_hash": item.content_hash,
            }
            for item in month_closures
        ],
    }


@dataclass(frozen=True, slots=True)
class TradingCalendarEvidence:
    """Versioned, content-addressed sequence of closed A-share months."""

    calendar_id: str
    version: int
    dataset_id: str
    snapshot_id: str
    manifest_hash: str
    certified_through: date
    authority_as_of: date
    month_closures: tuple[TradingCalendarMonthClosure, ...]
    payload_hash: str

    def __post_init__(self) -> None:
        """Reject partial, non-canonical, or content-drifting calendar evidence."""
        _validated_trading_calendar(self)

    @classmethod
    def create(
        cls,
        *,
        calendar_id: str,
        version: int,
        source: TradingCalendarSourceIdentity,
        month_closures: tuple[TradingCalendarMonthClosure, ...],
    ) -> TradingCalendarEvidence:
        """Construct one canonical calendar evidence identity."""
        raw_source = cast("object", source)
        if type(raw_source) is not TradingCalendarSourceIdentity:
            _fail("SPEC_INVALID", "invalid_trading_calendar_source_identity")
        typed_source = raw_source
        raw_closures = cast("object", month_closures)
        if type(raw_closures) is not tuple:
            _fail("SPEC_INVALID", "trading_calendar_closures_must_be_tuple")
        closures = cast("tuple[TradingCalendarMonthClosure, ...]", raw_closures)
        payload = _calendar_evidence_payload(
            calendar_id=calendar_id,
            version=version,
            source=typed_source,
            month_closures=closures,
        )
        return cls(
            calendar_id,
            version,
            typed_source.dataset_id,
            typed_source.snapshot_id,
            typed_source.manifest_hash,
            typed_source.certified_through,
            typed_source.authority_as_of,
            closures,
            _payload_hash(payload),
        )


def _validated_sessions(raw_sessions: object) -> tuple[date, ...]:
    if type(raw_sessions) is not tuple or not raw_sessions:
        _fail("SPEC_INVALID", "trading_sessions_must_be_non_empty_tuple")
    sessions: list[date] = []
    for raw_session in cast("tuple[object, ...]", raw_sessions):
        if type(raw_session) is not date:
            _fail("SPEC_INVALID", "invalid_trading_session")
        sessions.append(raw_session)
    if any(current >= following for current, following in pairwise(sessions)):
        _fail("SPEC_INVALID", "trading_sessions_not_strictly_increasing")
    return tuple(sessions)


def _validated_calendar_month(
    raw_value: object,
    *,
    reason: str,
) -> CalendarMonth:
    if type(raw_value) is not CalendarMonth:
        _fail("SPEC_INVALID", reason)
    value = raw_value
    _require_exact_int(value.year, field_name="calendar_month_year", minimum=1)
    month = _require_exact_int(
        value.month,
        field_name="calendar_month_number",
        minimum=1,
    )
    if month > _MONTHS_PER_YEAR:
        _fail("SPEC_INVALID", "invalid_calendar_month_number", maximum=12)
    return value


def _validated_calendar_day(raw_day: object) -> TradingCalendarDay:
    if type(raw_day) is not TradingCalendarDay:
        _fail("SPEC_INVALID", "invalid_trading_calendar_day")
    day = raw_day
    if type(day.calendar_date) is not date:
        _fail("SPEC_INVALID", "invalid_trading_calendar_date")
    if type(day.status) is not TradingCalendarDayStatus:
        _fail("SPEC_INVALID", "invalid_trading_calendar_day_status")
    return day


def _validated_month_closure(
    raw_closure: object,
) -> TradingCalendarMonthClosure:
    if type(raw_closure) is not TradingCalendarMonthClosure:
        _fail("SPEC_INVALID", "invalid_trading_calendar_month_closure")
    closure = raw_closure
    month = _validated_calendar_month(
        cast("object", closure.month),
        reason="invalid_trading_calendar_closure_month",
    )
    raw_days = cast("object", closure.days)
    if type(raw_days) is not tuple:
        _fail("SPEC_INVALID", "trading_calendar_days_must_be_tuple")
    days = tuple(
        _validated_calendar_day(item) for item in cast("tuple[object, ...]", raw_days)
    )
    last_day = monthrange(month.year, month.month)[1]
    expected_dates = tuple(
        date(month.year, month.month, day_number)
        for day_number in range(1, last_day + 1)
    )
    if tuple(item.calendar_date for item in days) != expected_dates:
        _fail(
            "SPEC_INVALID",
            "trading_calendar_month_not_fully_closed",
            month=str(month),
        )
    if any(
        item.calendar_date.weekday() >= _WEEKEND_START
        and item.status is TradingCalendarDayStatus.OPEN
        for item in days
    ):
        _fail("SPEC_INVALID", "a_share_weekend_cannot_be_open", month=str(month))
    open_session_count = sum(
        item.status is TradingCalendarDayStatus.OPEN for item in days
    )
    if open_session_count < _MIN_A_SHARE_COMPLETE_MONTH_OPEN_SESSIONS:
        _fail(
            "SPEC_INVALID",
            "a_share_complete_month_open_session_sanity_failed",
            month=str(month),
            minimum_open_sessions=_MIN_A_SHARE_COMPLETE_MONTH_OPEN_SESSIONS,
            observed_open_sessions=open_session_count,
        )
    if not is_canonical_content_hash(closure.content_hash):
        _fail("SPEC_INVALID", "invalid_trading_calendar_month_hash")
    if closure.content_hash != _payload_hash(_month_closure_payload(month, days)):
        _fail("SPEC_INVALID", "trading_calendar_month_hash_mismatch")
    return closure


def _validated_trading_calendar(
    raw_evidence: object,
) -> TradingCalendarEvidence:
    if type(raw_evidence) is not TradingCalendarEvidence:
        _fail("SPEC_INVALID", "invalid_trading_calendar_evidence")
    evidence = raw_evidence
    if not is_canonical_identity(evidence.calendar_id):
        _fail("SPEC_INVALID", "invalid_trading_calendar_id")
    if not all(
        is_canonical_identity(value)
        for value in (evidence.dataset_id, evidence.snapshot_id)
    ) or not is_canonical_content_hash(evidence.manifest_hash):
        _fail("SPEC_INVALID", "invalid_trading_calendar_source_identity")
    if (
        type(evidence.certified_through) is not date
        or type(evidence.authority_as_of) is not date
    ):
        _fail("SPEC_INVALID", "invalid_trading_calendar_certification_range")
    version = _require_exact_int(
        evidence.version,
        field_name="trading_calendar_version",
        minimum=1,
    )
    raw_closures = cast("object", evidence.month_closures)
    if type(raw_closures) is not tuple or not raw_closures:
        _fail("SPEC_INVALID", "trading_calendar_closures_must_be_non_empty_tuple")
    closures = tuple(
        _validated_month_closure(item)
        for item in cast("tuple[object, ...]", raw_closures)
    )
    if any(
        following.month != current.month.next()
        for current, following in pairwise(closures)
    ):
        _fail("SPEC_INVALID", "trading_calendar_months_not_contiguous")
    last_closed_date = closures[-1].days[-1].calendar_date
    if not (last_closed_date <= evidence.certified_through <= evidence.authority_as_of):
        _fail("SPEC_INVALID", "trading_calendar_exceeds_certified_authority_range")
    if not is_canonical_content_hash(evidence.payload_hash):
        _fail("SPEC_INVALID", "invalid_trading_calendar_payload_hash")
    source = TradingCalendarSourceIdentity(
        evidence.dataset_id,
        evidence.snapshot_id,
        evidence.manifest_hash,
        evidence.certified_through,
        evidence.authority_as_of,
    )
    expected_hash = _payload_hash(
        _calendar_evidence_payload(
            calendar_id=evidence.calendar_id,
            version=version,
            source=source,
            month_closures=closures,
        )
    )
    if evidence.payload_hash != expected_hash:
        _fail("SPEC_INVALID", "trading_calendar_payload_hash_mismatch")
    return evidence


def seal_trading_calendar(raw_evidence: object) -> TradingCalendarEvidence:
    """Copy one untrusted graph into exact immutable calendar value objects."""
    if type(raw_evidence) is not TradingCalendarEvidence:
        _fail("SPEC_INVALID", "invalid_trading_calendar_evidence")
    calendar_id = raw_evidence.calendar_id
    version = raw_evidence.version
    dataset_id = raw_evidence.dataset_id
    snapshot_id = raw_evidence.snapshot_id
    manifest_hash = raw_evidence.manifest_hash
    certified_through = raw_evidence.certified_through
    authority_as_of = raw_evidence.authority_as_of
    raw_closures = raw_evidence.month_closures
    payload_hash = raw_evidence.payload_hash
    if type(raw_closures) is not tuple:
        _fail("SPEC_INVALID", "trading_calendar_closures_must_be_tuple")
    closures: list[TradingCalendarMonthClosure] = []
    for raw_closure in raw_closures:
        if type(raw_closure) is not TradingCalendarMonthClosure:
            _fail("SPEC_INVALID", "invalid_trading_calendar_month_closure")
        raw_month = raw_closure.month
        raw_days = raw_closure.days
        content_hash = raw_closure.content_hash
        if type(raw_month) is not CalendarMonth or type(raw_days) is not tuple:
            _fail("SPEC_INVALID", "invalid_trading_calendar_month_closure")
        month = CalendarMonth(raw_month.year, raw_month.month)
        days: list[TradingCalendarDay] = []
        for raw_day in raw_days:
            if type(raw_day) is not TradingCalendarDay:
                _fail("SPEC_INVALID", "invalid_trading_calendar_day")
            calendar_date = raw_day.calendar_date
            status = raw_day.status
            days.append(TradingCalendarDay(calendar_date, status))
        closures.append(TradingCalendarMonthClosure(month, tuple(days), content_hash))
    return TradingCalendarEvidence(
        calendar_id,
        version,
        dataset_id,
        snapshot_id,
        manifest_hash,
        certified_through,
        authority_as_of,
        tuple(closures),
        payload_hash,
    )


def _sessions_by_month(
    sessions: tuple[date, ...],
    last_complete_month: CalendarMonth,
) -> dict[CalendarMonth, tuple[date, ...]]:
    grouped: dict[CalendarMonth, list[date]] = {}
    for session in sessions:
        month = CalendarMonth.from_date(session)
        if month > last_complete_month:
            _fail(
                "SPEC_INVALID",
                "trading_session_after_last_complete_month",
                session=session.isoformat(),
            )
        grouped.setdefault(month, []).append(session)
    if last_complete_month not in grouped:
        _fail(
            "SPEC_INVALID",
            "last_complete_month_has_no_sessions",
            month=str(last_complete_month),
        )
    return {month: tuple(values) for month, values in grouped.items()}


def _month_range(
    start: CalendarMonth,
    end: CalendarMonth,
) -> tuple[CalendarMonth, ...]:
    if start > end:
        return ()
    months: list[CalendarMonth] = []
    current = start
    while current <= end:
        months.append(current)
        current = current.next()
    return tuple(months)


def _complete_months(
    *,
    session_months: dict[CalendarMonth, tuple[date, ...]],
    strategy_eligible_start: date,
    last_complete_month: CalendarMonth,
) -> tuple[CalendarMonth, ...]:
    first_month = CalendarMonth.from_date(strategy_eligible_start)
    months = _month_range(first_month, last_complete_month)
    for month in months:
        if month not in session_months:
            _fail("SPEC_INVALID", "calendar_month_missing", month=str(month))
    if not months:
        return ()
    if strategy_eligible_start > session_months[months[0]][0]:
        return months[1:]
    return months


# Neutral sibling modules use these explicit support APIs; they remain outside the
# public value-object ``__all__`` surface.
calendar_evidence_payload = _calendar_evidence_payload
canonical_payload_hash = _payload_hash
complete_months = _complete_months
fail_validation = _fail
require_exact_int = _require_exact_int
sessions_by_month = _sessions_by_month
validate_calendar_month = _validated_calendar_month
validate_sessions = _validated_sessions
validate_trading_calendar = _validated_trading_calendar
