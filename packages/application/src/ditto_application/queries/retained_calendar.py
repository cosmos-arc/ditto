"""Trading sessions read from retained calendar evidence at a cutoff."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import NamedTuple

import polars as pl
from ditto_data.catalog.provider_payload import (
    ProviderPayloadArtifact,
    ProviderPayloadReader,
)
from ditto_data.catalog.source_snapshot import ProviderSnapshot, ProviderSnapshotReader


class RetainedCalendarAbsent(ValueError):
    """No retained calendar snapshot is visible at the requested cutoff."""


class RetainedCalendar(NamedTuple):
    """Open sessions plus the retained snapshot identity that produced them."""

    days: list[str]
    snapshot_id: str
    authority: dict[str, str]
    shard_sources: dict[str, str]
    revision_gaps: frozenset[str]


def calendar_has_single_source(
    calendar: RetainedCalendar, first_day: str, last_day: str
) -> bool:
    """Check the source of every consumed open or closed date."""
    sources = {
        calendar.shard_sources.get(snapshot_id)
        for day, snapshot_id in calendar.authority.items()
        if first_day <= day <= last_day
    }
    return len(sources) == 1 and None not in sources


def _observed_by(snapshot: ProviderSnapshot, cutoff: datetime) -> datetime:
    """
    Latest observation event this snapshot had actually received by the cutoff.

    A snapshot stays visible from its first ``created_at``; its revision
    recency at a cutoff is the newest observation event not after that
    cutoff, so replaying across cutoffs reproduces the observation order
    exactly, including intermediate re-observations.
    """
    return max(
        (event for event in getattr(snapshot, "observations", ()) if event <= cutoff),
        default=snapshot.created_at,
    )


class RetainedCalendarWindow(NamedTuple):
    """Open sessions, per-date authority, and each shard's provider source."""

    days: list[str]
    authority: dict[str, str]
    shard_sources: dict[str, str]
    revision_gaps: frozenset[str]


def calendar_has_complete_authority(
    calendar: RetainedCalendar | RetainedCalendarWindow,
    first_day: str,
    last_day: str,
) -> bool:
    """Require an explicit decision and no revision hole for each consumed date."""
    day = date.fromisoformat(first_day)
    final = date.fromisoformat(last_day)
    while day <= final:
        iso = day.isoformat()
        if iso not in calendar.authority or iso in calendar.revision_gaps:
            return False
        day += timedelta(days=1)
    return True


def _calendar_states(
    frame: pl.DataFrame, first_day: str, last_day: str
) -> dict[str, bool]:
    """Map every scheduled session in the interval to its open state."""
    if "trade_date" not in frame.columns or "is_open" not in frame.columns:
        raise RetainedCalendarAbsent("retained calendar is malformed")
    return {
        str(value): is_open is True
        for value, is_open in zip(frame["trade_date"], frame["is_open"], strict=True)
        if first_day <= str(value) <= last_day
    }


def _revision_gaps(
    snapshot: ProviderSnapshot,
    states: dict[str, bool],
    authorship: dict[str, tuple[bool, str]],
    first_day: str,
    last_day: str,
) -> set[str]:
    intervals = [(min(states), max(states))] if states else []
    request_start = getattr(snapshot, "request_start", None)
    request_end = getattr(snapshot, "request_end", None)
    if request_start is not None and request_end is not None:
        start = max(first_day, request_start)
        end = min(last_day, request_end)
        if start <= end:
            intervals.append((start, end))
    gaps: set[str] = set()
    for start, end in intervals:
        day = date.fromisoformat(start)
        final = date.fromisoformat(end)
        while day <= final:
            iso = day.isoformat()
            if iso not in states and iso in authorship:
                gaps.add(iso)
            day += timedelta(days=1)
    return gaps


def retained_calendar_window(
    *,
    snapshots: ProviderSnapshotReader,
    payloads: ProviderPayloadReader,
    cutoff: datetime,
    first_day: str,
    last_day: str,
) -> RetainedCalendarWindow:
    """
    Combine cutoff-visible retained calendar shards into one window.

    Production calendar evidence arrives as annual bootstrap chunks plus
    current-year daily shards, so shards are selected by payload coverage,
    not request bounds. Revisions apply oldest-to-newest and the newest
    revision wins per date, so a corrected closure can never be masked by a
    stale open day. Whether shards come from one provider source is judged
    by the caller over the sessions a window actually consumes.
    """
    shards = sorted(
        (
            snapshot
            for snapshot in snapshots.list_snapshots(dataset_id="calendar")
            if snapshot.payload_retained and snapshot.created_at <= cutoff
        ),
        key=lambda item: (_observed_by(item, cutoff), item.snapshot_id),
    )
    if not shards:
        raise RetainedCalendarAbsent("retained calendar is absent or future")
    authorship: dict[str, tuple[bool, str]] = {}
    revision_gaps: set[str] = set()
    shard_sources: dict[str, str] = {}
    read_payloads: dict[str, pl.DataFrame] = {}
    for snapshot in shards:
        if snapshot.payload_uri is None:
            raise RetainedCalendarAbsent("retained calendar is absent or future")
        shard_sources[snapshot.snapshot_id] = snapshot.source
        frame = read_payloads.get(snapshot.checksum)
        if frame is None:
            frame = payloads.read_payload(
                ProviderPayloadArtifact(
                    dataset_id=snapshot.dataset_id,
                    source=snapshot.source,
                    checksum=snapshot.checksum,
                    row_count=snapshot.row_count,
                    uri=snapshot.payload_uri,
                )
            )
            read_payloads[snapshot.checksum] = frame
        states = _calendar_states(frame, first_day, last_day)
        revision_gaps.update(
            _revision_gaps(snapshot, states, authorship, first_day, last_day)
        )
        for day, is_open in states.items():
            authorship[day] = (is_open, snapshot.snapshot_id)
            revision_gaps.discard(day)
    days = sorted(day for day, state in authorship.items() if state[0])
    if not days:
        raise RetainedCalendarAbsent("retained calendar is malformed")
    return RetainedCalendarWindow(
        days,
        {day: state[1] for day, state in authorship.items()},
        shard_sources,
        frozenset(revision_gaps),
    )


def retained_trading_days(
    *,
    snapshots: ProviderSnapshotReader,
    payloads: ProviderPayloadReader,
    cutoff: datetime,
    first_day: str,
) -> RetainedCalendar:
    """
    Return open sessions composed from calendar shards covering first_day.

    The trading-calendar read model is unversioned, so only retained provider
    payloads visible at the cutoff are used; shards that cannot cover the
    requested date (for example a re-observed prior-year chunk) never win by
    recency alone. The first eligible session supplies the authority identity.
    """
    window = retained_calendar_window(
        snapshots=snapshots,
        payloads=payloads,
        cutoff=cutoff,
        first_day=first_day,
        last_day="9999-12-31",
    )
    return RetainedCalendar(
        window.days,
        window.authority[window.days[0]],
        window.authority,
        window.shard_sources,
        window.revision_gaps,
    )
