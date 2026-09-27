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
    gap_sources: dict[str, str]


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
    gap_sources: dict[str, str]


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
    frame: pl.DataFrame, snapshot: ProviderSnapshot, first_day: str, last_day: str
) -> dict[str, bool]:
    """
    Map every scheduled session in the interval to its open state.

    A payload row outside its own snapshot's request bounds was never
    covered by that observation; folding it would let the calendar claim
    authority beyond its declared window, so it fails closed like the
    technical payload reader. A consumed ``is_open`` that is not an actual
    Boolean is malformed evidence: silently coercing it to closed would let
    an all-malformed window pass as authoritatively closed under
    ``allow_closed_window=True``.
    """
    if "trade_date" not in frame.columns or "is_open" not in frame.columns:
        raise RetainedCalendarAbsent("retained calendar is malformed")
    states: dict[str, bool] = {}
    for value, is_open in zip(frame["trade_date"], frame["is_open"], strict=True):
        day = str(value)
        if not snapshot.request_start <= day <= snapshot.request_end:
            raise RetainedCalendarAbsent(
                "calendar payload row outside snapshot request bounds"
            )
        if first_day <= day <= last_day:
            if is_open is not True and is_open is not False:
                raise RetainedCalendarAbsent("calendar is_open state is not a boolean")
            states[day] = is_open
    return states


def _revision_gaps(
    snapshot: ProviderSnapshot,
    states: dict[str, bool],
    authorship: dict[str, tuple[bool, str]],
    first_day: str,
    last_day: str,
) -> dict[str, str]:
    """Days this shard supersedes into gaps, mapped to the shard itself."""
    intervals = [(min(states), max(states))] if states else []
    request_start = getattr(snapshot, "request_start", None)
    request_end = getattr(snapshot, "request_end", None)
    if request_start is not None and request_end is not None:
        start = max(first_day, request_start)
        end = min(last_day, request_end)
        if start <= end:
            intervals.append((start, end))
    gaps: dict[str, str] = {}
    for start, end in intervals:
        day = date.fromisoformat(start)
        final = date.fromisoformat(end)
        while day <= final:
            iso = day.isoformat()
            if iso not in states and iso in authorship:
                gaps[iso] = snapshot.snapshot_id
            day += timedelta(days=1)
    return gaps


def _is_verified_empty_observation(snapshot: ProviderSnapshot) -> bool:
    return (
        not snapshot.payload_retained
        and snapshot.row_count == 0
        and dict(snapshot.response_metadata).get("snapshot_layer")
        == "verified_empty_provider_observation"
    )


def _calendar_exchange_scope(snapshot: ProviderSnapshot) -> str | None:
    """
    Resolve a calendar shard's exchange scope.

    Production registers one calendar through the Tushare adapter without an
    exchange partition; by the A-share contract that unmarked shard is the
    shared session schedule (coordinated holidays) valid across
    SSE/SZSE/BSE. An explicit ``exchange=`` partition scopes a shard to that
    exchange, and a mismatched explicit scope never serves another
    exchange's chart.
    """
    asset = cast("DataAssetRef | None", getattr(snapshot, "canonical_asset", None))
    for key in asset.partition_keys if asset is not None else ():
        if key.startswith("exchange="):
            return key.removeprefix("exchange=")
    return None


def _calendar_serves_exchange(snapshot: ProviderSnapshot, exchange: str | None) -> bool:
    """
    Whether a calendar shard may serve a consumer of the given exchange.

    An unmarked shard is the shared A-share schedule and serves every
    consumer. An explicitly scoped shard serves only a consumer requesting
    that exchange; the shared view (``exchange=None``) therefore never
    mixes scoped shards in.
    """
    scope = _calendar_exchange_scope(snapshot)
    return scope is None or scope == exchange


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
    gap_sources: dict[str, str] = field(default_factory=dict)
    shard_sources: dict[str, str] = field(default_factory=dict)
    read_payloads: dict[str, pl.DataFrame] = field(default_factory=dict)


def _calendar_plans(
    shards: list[ProviderSnapshot],
    payloads: ProviderPayloadReader,
    fold: _CalendarFold,
    first_day: str,
    last_day: str,
    cutoff: datetime,
) -> list[tuple[ProviderSnapshot, datetime, dict[str, bool]]]:
    """Read each retained shard once into (snapshot, observed, states)."""
    plans: list[tuple[ProviderSnapshot, datetime, dict[str, bool]]] = []
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
        states = _calendar_states(frame, snapshot, first_day, last_day)
        plans.append((snapshot, snapshot_observed_by(snapshot, cutoff), states))
    return plans


def _reject_tied_omissions(
    plans: list[tuple[ProviderSnapshot, datetime, dict[str, bool]]],
    first_day: str,
    last_day: str,
) -> None:
    """
    Fail closed when tied shards disagree by omission.

    A shard whose request bounds cover a day it omits, while a
    same-observation peer supplies that day, has no PIT order: the gap
    would depend on which content-derived snapshot ID folds first.
    """
    supplied_at: dict[str, set[datetime]] = {}
    for _, observed, states in plans:
        for day in states:
            supplied_at.setdefault(day, set()).add(observed)
    for snapshot, observed, states in plans:
        start = max(first_day, snapshot.request_start)
        end = min(last_day, snapshot.request_end)
        day = date.fromisoformat(start)
        final = date.fromisoformat(end)
        while day <= final:
            iso = day.isoformat()
            if (
                iso not in states
                and iso in supplied_at
                and observed in supplied_at[iso]
            ):
                raise RetainedCalendarAbsent(
                    "retained calendar revisions tie with an omitted session"
                )
            day += timedelta(days=1)


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
    tied shards leave either the day's state, its credited authority
    snapshot, or its omission gap dependent on ID ordering, so tied
    conflicting states, tied distinct authorities, and tied
    supply-versus-omission decisions all fail closed.
    """
    plans = _calendar_plans(shards, payloads, fold, first_day, last_day, cutoff)
    _reject_tied_omissions(plans, first_day, last_day)
    for snapshot, observed, states in plans:
        new_gaps = _revision_gaps(
            snapshot, states, fold.authorship, first_day, last_day
        )
        fold.revision_gaps.update(new_gaps)
        fold.gap_sources.update(new_gaps)
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
            fold.gap_sources.pop(day, None)


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
                fold.gap_sources[day] = snapshot.snapshot_id


def retained_calendar_window(
    *,
    snapshots: ProviderSnapshotReader,
    payloads: ProviderPayloadReader,
    cutoff: datetime,
    first_day: str,
    last_day: str,
    allow_closed_window: bool = False,
    exchange: str | None = None,
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

    ``exchange`` scopes shard selection. Calendar shards without an exchange
    partition are the shared A-share schedule (coordinated sessions across
    SSE/SZSE/BSE); the default ``exchange=None`` shared view consumes only
    those unmarked shards, and an explicit exchange additionally accepts a
    matching ``exchange=`` partition — a mismatched explicit scope never
    serves another exchange. Multi-instrument consumers stay on the shared
    view until per-exchange ingestion registers scoped shards.
    """
    ordered = sorted(
        (
            snapshot
            for snapshot in snapshots.list_snapshots(dataset_id="calendar")
            if snapshot.created_at <= cutoff
            and (snapshot.payload_retained or _is_verified_empty_observation(snapshot))
            and _calendar_serves_exchange(snapshot, exchange)
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
        fold.gap_sources,
    )


def retained_trading_days(
    *,
    snapshots: ProviderSnapshotReader,
    payloads: ProviderPayloadReader,
    cutoff: datetime,
    first_day: str,
    exchange: str | None = None,
) -> RetainedCalendar:
    """
    Return open sessions composed from calendar shards covering first_day.

    The trading-calendar read model is unversioned, so only retained provider
    payloads visible at the cutoff are used; shards that cannot cover the
    requested date (for example a re-observed prior-year chunk) never win by
    recency alone. The first eligible session supplies the authority identity.
    ``exchange`` follows the shared-schedule contract of
    ``retained_calendar_window``.
    """
    window = retained_calendar_window(
        snapshots=snapshots,
        payloads=payloads,
        cutoff=cutoff,
        first_day=first_day,
        last_day="9999-12-31",
        exchange=exchange,
    )
    return RetainedCalendar(
        window.days,
        window.authority[window.days[0]],
        window.authority,
        window.shard_sources,
        window.revision_gaps,
        window.gap_sources,
    )
