"""Trading sessions read from retained calendar evidence at a cutoff."""

from __future__ import annotations

from datetime import datetime

from ditto_data.catalog.provider_payload import (
    ProviderPayloadArtifact,
    ProviderPayloadReader,
)
from ditto_data.catalog.source_snapshot import ProviderSnapshotReader


class RetainedCalendarAbsent(ValueError):
    """No retained calendar snapshot is visible at the requested cutoff."""


def retained_trading_days(
    *,
    snapshots: ProviderSnapshotReader,
    payloads: ProviderPayloadReader,
    cutoff: datetime,
) -> list[str]:
    """
    Return open sessions from the calendar snapshot newest at the cutoff.

    The trading-calendar read model is unversioned, so the retained provider
    payload newest at the cutoff is the only basis that cannot consume later
    calendar refreshes.
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
    return sorted(
        str(value)
        for value, is_open in zip(frame["trade_date"], frame["is_open"], strict=True)
        if is_open is True
    )
