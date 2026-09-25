"""Retained calendar composition and re-observation ordering."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any, cast

from ditto_application.queries.retained_calendar import (
    retained_calendar_window,
    retained_trading_days,
)
from ditto_data.catalog.provider_payload import ProviderPayloadReader
from ditto_data.catalog.source_snapshot import ProviderSnapshotReader


class _Frame(dict):
    """Minimal frame double exposing the trade_date/is_open columns."""

    columns = ("trade_date", "is_open")


def _shard(
    snapshot_id: str,
    *,
    created_at: datetime,
    days: list[str],
    flags: list[bool] | None = None,
    last_observed_at: datetime | None = None,
) -> Any:
    checksum = f"{abs(hash(snapshot_id)) % 10**32:032x}"
    return SimpleNamespace(
        dataset_id="calendar",
        source="recorded",
        snapshot_id=snapshot_id,
        created_at=created_at,
        last_observed_at=last_observed_at,
        payload_retained=True,
        payload_uri=f"provider_payloads/recorded/calendar/{checksum}.parquet",
        checksum=checksum,
        row_count=len(days),
        request_start=days[0],
        request_end=days[-1],
        _days=days,
        _flags=flags or [True] * len(days),
    )


def _readers(shards: list[Any]) -> tuple[Any, Any]:
    by_checksum = {shard.checksum: shard for shard in shards}
    snapshots = cast(
        ProviderSnapshotReader,
        SimpleNamespace(
            list_snapshots=lambda dataset_id: (
                shards if dataset_id == "calendar" else []
            ),
        ),
    )
    payloads = cast(
        ProviderPayloadReader,
        SimpleNamespace(
            read_payload=lambda artifact: _Frame(
                trade_date=list(by_checksum[artifact.checksum]._days),
                is_open=list(by_checksum[artifact.checksum]._flags),
            )
        ),
    )
    return snapshots, payloads


def test_open_closed_reopen_replays_per_cutoff() -> None:
    """A→B→A(re) yields A, then B, then A as the cutoff advances."""
    utc = UTC
    original = _shard(
        "snapshot:recorded:calendar:open",
        created_at=datetime(2026, 6, 1, tzinfo=utc),
        days=["2026-06-01", "2026-06-02"],
        last_observed_at=datetime(2026, 6, 3, tzinfo=utc),
    )
    closed = _shard(
        "snapshot:recorded:calendar:closed",
        created_at=datetime(2026, 6, 2, tzinfo=utc),
        days=["2026-06-01", "2026-06-02"],
        flags=[True, False],
    )
    snapshots, payloads = _readers([original, closed])

    before_supersede = retained_calendar_window(
        snapshots=snapshots,
        payloads=payloads,
        cutoff=datetime(2026, 6, 1, 12, tzinfo=utc),
        first_day="2026-06-01",
        last_day="2026-06-30",
    )
    assert before_supersede.days == ["2026-06-01", "2026-06-02"]

    after_supersede = retained_calendar_window(
        snapshots=snapshots,
        payloads=payloads,
        cutoff=datetime(2026, 6, 2, 12, tzinfo=utc),
        first_day="2026-06-01",
        last_day="2026-06-30",
    )
    assert after_supersede.days == ["2026-06-01"]

    after_reopen = retained_calendar_window(
        snapshots=snapshots,
        payloads=payloads,
        cutoff=datetime(2026, 6, 3, 12, tzinfo=utc),
        first_day="2026-06-01",
        last_day="2026-06-30",
    )
    assert after_reopen.days == ["2026-06-01", "2026-06-02"]

    newest = retained_trading_days(
        snapshots=snapshots,
        payloads=payloads,
        cutoff=datetime(2026, 6, 3, 12, tzinfo=utc),
    )
    assert newest.days == ["2026-06-01", "2026-06-02"]
    assert newest.snapshot_id == original.snapshot_id
