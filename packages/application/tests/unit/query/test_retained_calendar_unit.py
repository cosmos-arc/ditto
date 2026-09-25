"""Retained calendar composition and re-observation ordering."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any, cast

import pytest
from ditto_application.exceptions import AppProcessError
from ditto_application.queries.etf_paper_handoff_facts import _next_trading_day
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
    observations: tuple[datetime, ...] = (),
    source: str = "recorded",
) -> Any:
    checksum = f"{abs(hash(snapshot_id)) % 10**32:032x}"
    return SimpleNamespace(
        dataset_id="calendar",
        source=source,
        snapshot_id=snapshot_id,
        created_at=created_at,
        observations=observations,
        payload_retained=True,
        payload_uri=f"provider_payloads/{source}/calendar/{checksum}.parquet",
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
        observations=(
            datetime(2026, 6, 1, tzinfo=utc),
            datetime(2026, 6, 3, tzinfo=utc),
        ),
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
        first_day="2026-06-01",
    )
    assert newest.days == ["2026-06-01", "2026-06-02"]


def test_replay_between_intermediate_observations_uses_event_history() -> None:
    """A later routine re-observation never erases intermediate order."""
    utc = UTC
    original = _shard(
        "snapshot:recorded:calendar:open",
        created_at=datetime(2026, 6, 1, tzinfo=utc),
        days=["2026-06-01", "2026-06-02"],
        observations=(
            datetime(2026, 6, 1, tzinfo=utc),
            datetime(2026, 6, 3, tzinfo=utc),
            datetime(2026, 6, 5, tzinfo=utc),
        ),
    )
    closed = _shard(
        "snapshot:recorded:calendar:closed",
        created_at=datetime(2026, 6, 2, tzinfo=utc),
        days=["2026-06-01", "2026-06-02"],
        flags=[True, False],
    )
    snapshots, payloads = _readers([original, closed])

    at_t4 = retained_calendar_window(
        snapshots=snapshots,
        payloads=payloads,
        cutoff=datetime(2026, 6, 4, 12, tzinfo=utc),
        first_day="2026-06-01",
        last_day="2026-06-30",
    )
    # t3 的 A 重观察晚于 B(t2)，t4 回放必须仍由 A 胜出。
    assert at_t4.days == ["2026-06-01", "2026-06-02"]


@pytest.mark.pit
def test_newer_calendar_revision_cannot_inherit_a_missing_date() -> None:
    original = _shard(
        "snapshot:recorded:calendar:original",
        created_at=datetime(2026, 6, 1, tzinfo=UTC),
        days=["2026-06-01", "2026-06-02", "2026-06-03"],
    )
    incomplete = _shard(
        "snapshot:recorded:calendar:revision",
        created_at=datetime(2026, 6, 2, tzinfo=UTC),
        days=["2026-06-01", "2026-06-03"],
    )
    snapshots, payloads = _readers([original, incomplete])

    window = retained_calendar_window(
        snapshots=snapshots,
        payloads=payloads,
        cutoff=datetime(2026, 6, 3, tzinfo=UTC),
        first_day="2026-06-01",
        last_day="2026-06-03",
    )
    assert window.revision_gaps == frozenset({"2026-06-02"})

    with pytest.raises(AppProcessError, match="calendar is incomplete"):
        _next_trading_day(
            snapshots=snapshots,
            payloads=payloads,
            cutoff=datetime(2026, 6, 3, tzinfo=UTC),
            signal_date="2026-06-01",
        )


def test_paper_calendar_ignores_newer_observation_of_old_shard() -> None:
    """A routine observation of last year's shard cannot hide current dates."""
    old = _shard(
        "snapshot:recorded:calendar:2025",
        created_at=datetime(2025, 1, 1, tzinfo=UTC),
        days=["2025-12-30", "2025-12-31"],
        observations=(datetime(2026, 9, 3, tzinfo=UTC),),
    )
    current = _shard(
        "snapshot:recorded:calendar:2026",
        created_at=datetime(2026, 9, 2, tzinfo=UTC),
        days=["2026-09-02", "2026-09-03", "2026-09-04"],
    )
    snapshots, payloads = _readers([old, current])

    calendar = retained_trading_days(
        snapshots=snapshots,
        payloads=payloads,
        cutoff=datetime(2026, 9, 3, 12, tzinfo=UTC),
        first_day="2026-09-02",
    )
    assert calendar.days == ["2026-09-02", "2026-09-03", "2026-09-04"]
    assert calendar.snapshot_id == current.snapshot_id


@pytest.mark.pit
def test_paper_handoff_rejects_mixed_source_next_session() -> None:
    primary = _shard(
        "snapshot:primary:calendar",
        created_at=datetime(2026, 9, 2, tzinfo=UTC),
        days=["2026-09-02", "2026-09-03"],
    )
    secondary = _shard(
        "snapshot:secondary:calendar",
        created_at=datetime(2026, 9, 2, 1, tzinfo=UTC),
        days=["2026-09-03"],
        source="secondary",
    )
    snapshots, payloads = _readers([primary, secondary])

    with pytest.raises(AppProcessError, match="mixes provider sources"):
        _next_trading_day(
            snapshots=snapshots,
            payloads=payloads,
            cutoff=datetime(2026, 9, 2, 2, tzinfo=UTC),
            signal_date="2026-09-02",
        )
