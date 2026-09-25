"""Trading sessions read from retained calendar evidence at a cutoff."""

from __future__ import annotations

from datetime import datetime
from typing import NamedTuple

import polars as pl
from ditto_data.catalog.provider_payload import (
    ProviderPayloadArtifact,
    ProviderPayloadReader,
)
from ditto_data.catalog.source_snapshot import ProviderSnapshotReader


class RetainedCalendarAbsent(ValueError):
    """No retained calendar snapshot is visible at the requested cutoff."""


class RetainedCalendar(NamedTuple):
    """Open sessions plus the retained snapshot identity that produced them."""

    days: list[str]
    snapshot_id: str


class RetainedCalendarWindow(NamedTuple):
    """Open sessions, per-date authority, and each shard's provider source."""

    days: list[str]
    authority: dict[str, str]
    shard_sources: dict[str, str]


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
            if snapshot.payload_retained
            and (snapshot.last_observed_at or snapshot.created_at) <= cutoff
            and snapshot.request_end >= first_day
        ),
        key=lambda item: (item.last_observed_at or item.created_at, item.snapshot_id),
    )
    if not shards:
        raise RetainedCalendarAbsent("retained calendar is absent or future")
    authorship: dict[str, tuple[bool, str]] = {}
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
        for day, is_open in _calendar_states(frame, first_day, last_day).items():
            authorship[day] = (is_open, snapshot.snapshot_id)
    days = sorted(day for day, state in authorship.items() if state[0])
    if not days:
        raise RetainedCalendarAbsent("retained calendar is malformed")
    return RetainedCalendarWindow(
        days,
        {day: state[1] for day, state in authorship.items()},
        shard_sources,
    )


def retained_trading_days(
    *,
    snapshots: ProviderSnapshotReader,
    payloads: ProviderPayloadReader,
    cutoff: datetime,
) -> RetainedCalendar:
    """
    Return open sessions from the calendar snapshot newest at the cutoff.

    The trading-calendar read model is unversioned, so the retained provider
    payload newest at the cutoff is the only basis that cannot consume later
    calendar refreshes. The selected snapshot identity travels with the days so
    results can name the exact calendar revision behind their window.
    """
    candidates = [
        snapshot
        for snapshot in snapshots.list_snapshots(dataset_id="calendar")
        if snapshot.payload_retained and snapshot.created_at <= cutoff
    ]
    if not candidates:
        raise RetainedCalendarAbsent("retained calendar is absent or future")
    snapshot = max(candidates, key=lambda item: (item.created_at, item.snapshot_id))
    if snapshot.payload_uri is None:
        raise RetainedCalendarAbsent("retained calendar is absent or future")
    frame = payloads.read_payload(
        ProviderPayloadArtifact(
            dataset_id=snapshot.dataset_id,
            source=snapshot.source,
            checksum=snapshot.checksum,
            row_count=snapshot.row_count,
            uri=snapshot.payload_uri,
        )
    )
    return RetainedCalendar(
        days=sorted(
            day
            for day, is_open in _calendar_states(
                frame, "0000-01-01", "9999-12-31"
            ).items()
            if is_open
        ),
        snapshot_id=snapshot.snapshot_id,
    )
