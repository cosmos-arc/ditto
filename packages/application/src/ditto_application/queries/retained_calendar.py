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
    """Open sessions in one interval plus every contributing shard identity."""

    days: list[str]
    snapshot_ids: tuple[str, ...]


def _open_sessions(frame: pl.DataFrame, first_day: str, last_day: str) -> set[str]:
    """Extract open sessions inside the bounded interval or fail closed."""
    if "trade_date" not in frame.columns or "is_open" not in frame.columns:
        raise RetainedCalendarAbsent("retained calendar is malformed")
    return {
        str(value)
        for value, is_open in zip(frame["trade_date"], frame["is_open"], strict=True)
        if is_open is True and first_day <= str(value) <= last_day
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
    Union every cutoff-visible retained calendar shard covering the interval.

    Production calendar evidence arrives as annual bootstrap chunks plus the
    current-year daily shard, so one lookback usually spans several snapshots;
    each shard keeps its own immutable identity for result lineage.
    """
    shards = sorted(
        (
            snapshot
            for snapshot in snapshots.list_snapshots(dataset_id="calendar")
            if snapshot.payload_retained
            and snapshot.created_at <= cutoff
            and snapshot.request_end >= first_day
            and snapshot.request_start <= last_day
        ),
        key=lambda item: (item.request_start, item.snapshot_id),
    )
    if not shards:
        raise RetainedCalendarAbsent("retained calendar is absent or future")
    days: set[str] = set()
    snapshot_ids: list[str] = []
    for snapshot in shards:
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
        shard_days = _open_sessions(frame, first_day, last_day)
        if shard_days:
            days.update(shard_days)
            snapshot_ids.append(snapshot.snapshot_id)
    if not days:
        raise RetainedCalendarAbsent("retained calendar is malformed")
    return RetainedCalendarWindow(sorted(days), tuple(snapshot_ids))


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
        days=sorted(_open_sessions(frame, "0000-01-01", "9999-12-31")),
        snapshot_id=snapshot.snapshot_id,
    )
