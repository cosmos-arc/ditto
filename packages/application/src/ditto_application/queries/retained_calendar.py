"""Trading sessions read from retained calendar evidence at a cutoff."""

from __future__ import annotations

from datetime import datetime
from typing import NamedTuple

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
    if "trade_date" not in frame.columns or "is_open" not in frame.columns:
        raise RetainedCalendarAbsent("retained calendar is malformed")
    return RetainedCalendar(
        days=sorted(
            str(value)
            for value, is_open in zip(
                frame["trade_date"], frame["is_open"], strict=True
            )
            if is_open is True
        ),
        snapshot_id=snapshot.snapshot_id,
    )
