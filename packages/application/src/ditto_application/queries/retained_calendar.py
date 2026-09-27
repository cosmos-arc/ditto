"""Trading sessions read from retained calendar evidence at a cutoff."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import NamedTuple, cast

import polars as pl
from ditto_data.catalog import DataAssetRef
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
    calendar: RetainedCalendar | RetainedCalendarWindow,
    first_day: str,
    last_day: str,
) -> bool:
    """Check the source of every consumed open or closed date."""
    sources = {
        calendar.shard_sources.get(snapshot_id)
        for day, snapshot_id in calendar.authority.items()
        if first_day <= day <= last_day
    }
    return len(sources) == 1 and None not in sources


def snapshot_observed_by(snapshot: ProviderSnapshot, cutoff: datetime) -> datetime:
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


def _is_verified_empty_observation(snapshot: ProviderSnapshot) -> bool:
    return (
        not snapshot.payload_retained
        and snapshot.row_count == 0
        and dict(snapshot.response_metadata).get("snapshot_layer")
        == "verified_empty_provider_observation"
    )


def _calendar_exchange_scope(snapshot: ProviderSnapshot) -> str:
    """
    Resolve a calendar shard's exchange scope.

    Production registers the calendar through the Tushare adapter whose
    exchange parameter defaults to SSE and stamps no exchange partition,
    so an unmarked shard is SSE by the registration contract; an explicit
    ``exchange=`` partition scopes later per-exchange registrations.
    """
    asset = cast("DataAssetRef | None", getattr(snapshot, "canonical_asset", None))
    for key in asset.partition_keys if asset is not None else ():
        if key.startswith("exchange="):
            return key.removeprefix("exchange=")
    return "SSE"


def _empty_observation_gaps(
    snapshot: ProviderSnapshot,
    authorship: dict[str, tuple[bool, str]],
    first_day: str,
    last_day: str,
) -> set[str]:
    """Days an empty observation supersedes: already-authored covered days."""
    start = max(first_day, snapshot.request_start)
    end = min(last_day, snapshot.request_end)
    gaps: set[str] = set()
    day = date.fromisoformat(start)
    final = date.fromisoformat(end)
    while day <= final:
        iso = day.isoformat()
        if iso in authorship:
            gaps.add(iso)
        day += timedelta(days=1)
    return gaps


@dataclass
class _CalendarFold:
    """Mutable per-window calendar combination state."""

    authorship: dict[str, tuple[bool, str]] = field(default_factory=dict)
    authorship_observed: dict[str, datetime] = field(default_factory=dict)
    revision_gaps: set[str] = field(default_factory=set)
    shard_sources: dict[str, str] = field(default_factory=dict)
    read_payloads: dict[str, pl.DataFrame] = field(default_factory=dict)


def _combine_retained_shards(
    shards: list[ProviderSnapshot],
    payloads: ProviderPayloadReader,
    fold: _CalendarFold,
    first_day: str,
    last_day: str,
    cutoff: datetime,
) -> None:
    """
    Fold retained shards oldest-to-newest into per-day authority.

    Equal observation timestamps do not establish revision order: distinct
    tied shards leave either the day's state or its credited authority
    snapshot dependent on ID ordering, so both ties fail closed.
    """
    for snapshot in shards:
        if snapshot.payload_uri is None:
            raise RetainedCalendarAbsent("retained calendar is absent or future")
        fold.shard_sources[snapshot.snapshot_id] = snapshot.source
        frame = fold.read_payloads.get(snapshot.checksum)
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
            fold.read_payloads[snapshot.checksum] = frame
        states = _calendar_states(frame, first_day, last_day)
        fold.revision_gaps.update(
            _revision_gaps(snapshot, states, fold.authorship, first_day, last_day)
        )
        observed = snapshot_observed_by(snapshot, cutoff)
        for day, is_open in states.items():
            prior = fold.authorship.get(day)
            if prior is not None and fold.authorship_observed.get(day) == observed:
                if prior[0] != is_open:
                    raise RetainedCalendarAbsent(
                        "retained calendar revisions tie with conflicting states"
                    )
                if prior[1] != snapshot.snapshot_id:
                    raise RetainedCalendarAbsent(
                        "retained calendar revisions tie with ambiguous authority"
                    )
            fold.authorship[day] = (is_open, snapshot.snapshot_id)
            fold.authorship_observed[day] = observed
            fold.revision_gaps.discard(day)


def _apply_empty_observations(
    empties: list[ProviderSnapshot],
    fold: _CalendarFold,
    first_day: str,
    last_day: str,
    cutoff: datetime,
) -> None:
    """
    Apply verified-empty observations after retained shards.

    Running empties against the final retained authority keeps tie rejection
    independent of content-derived snapshot ID ordering. A tie between an
    empty observation and the day's retained authority has no PIT order; a
    strictly newer empty observation supersedes the day into a revision gap.
    """
    for snapshot in empties:
        observed = snapshot_observed_by(snapshot, cutoff)
        for day in _empty_observation_gaps(
            snapshot, fold.authorship, first_day, last_day
        ):
            if fold.authorship_observed[day] == observed:
                raise RetainedCalendarAbsent(
                    "retained calendar revisions tie with an empty observation"
                )
            if fold.authorship_observed[day] < observed:
                fold.revision_gaps.add(day)


def retained_calendar_window(
    *,
    snapshots: ProviderSnapshotReader,
    payloads: ProviderPayloadReader,
    cutoff: datetime,
    first_day: str,
    last_day: str,
    allow_closed_window: bool = False,
    exchange: str = "SSE",
) -> RetainedCalendarWindow:
    """
    Combine cutoff-visible retained calendar shards into one window.

    Production calendar evidence arrives as annual bootstrap chunks plus
    current-year daily shards, so shards are selected by payload coverage,
    not request bounds. Revisions apply oldest-to-newest and the newest
    revision wins per date, so a corrected closure can never be masked by a
    stale open day. Whether shards come from one provider source is judged
    by the caller over the sessions a window actually consumes.

    A newer verified-empty calendar observation carries no payload but is
    still revision evidence: every already-authored day it supersedes
    becomes a revision gap, so the affected interval fails closed instead of
    silently serving the superseded calendar. A yet-newer retained shard
    re-covers the day and clears the gap. Retained shards are combined
    before empty observations so a tie between them is detected regardless
    of content-derived snapshot ID ordering.
    """
    ordered = sorted(
        (
            snapshot
            for snapshot in snapshots.list_snapshots(dataset_id="calendar")
            if snapshot.created_at <= cutoff
            and (snapshot.payload_retained or _is_verified_empty_observation(snapshot))
            and _calendar_exchange_scope(snapshot) == exchange
        ),
        key=lambda item: (snapshot_observed_by(item, cutoff), item.snapshot_id),
    )
    shards = [item for item in ordered if item.payload_retained]
    if not shards:
        raise RetainedCalendarAbsent("retained calendar is absent or future")
    empties = [item for item in ordered if not item.payload_retained]
    fold = _CalendarFold()
    _combine_retained_shards(shards, payloads, fold, first_day, last_day, cutoff)
    _apply_empty_observations(empties, fold, first_day, last_day, cutoff)
    authorship = fold.authorship
    days = sorted(day for day, state in authorship.items() if state[0])
    if not days and (not allow_closed_window or not authorship):
        raise RetainedCalendarAbsent("retained calendar is malformed")
    return RetainedCalendarWindow(
        days,
        {day: state[1] for day, state in authorship.items()},
        fold.shard_sources,
        frozenset(fold.revision_gaps),
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
