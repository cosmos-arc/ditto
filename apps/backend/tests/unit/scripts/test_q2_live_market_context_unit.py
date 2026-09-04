"""Unit contracts for the Q2 live MarketContext acceptance driver."""

from __future__ import annotations

from datetime import UTC, date, datetime
from types import SimpleNamespace

import polars as pl
import pytest
from ditto_apps.scripts.q2_live_market_context import (
    inspect_global_session_visibility,
    select_interval_snapshot_ids,
)


@pytest.mark.unit
def test_select_interval_snapshot_ids_rejects_point_snapshot_for_range() -> None:
    snapshots = (
        SimpleNamespace(
            dataset_id="index_daily",
            request_start="2024-03-29",
            request_end="2024-03-29",
            snapshot_id="snapshot-point",
            payload_retained=True,
            payload_uri="point.parquet",
        ),
        SimpleNamespace(
            dataset_id="index_daily",
            request_start="2024-02-01",
            request_end="2024-03-29",
            snapshot_id="snapshot-range-b",
            payload_retained=True,
            payload_uri="range-b.parquet",
        ),
        SimpleNamespace(
            dataset_id="index_daily",
            request_start="2024-02-01",
            request_end="2024-03-29",
            snapshot_id="snapshot-range-a",
            payload_retained=True,
            payload_uri="range-a.parquet",
        ),
    )

    assert select_interval_snapshot_ids(
        dataset_id="index_daily",
        target_from=date(2024, 2, 1),
        target_to=date(2024, 3, 29),
        snapshots=snapshots,
    ) == ("snapshot-range-a", "snapshot-range-b")


@pytest.mark.unit
def test_global_session_visibility_excludes_same_day_future_close_at_open() -> None:
    frame = pl.DataFrame(
        {
            "source_ticker": ["N225"],
            "timezone": ["Asia/Tokyo"],
            "event_time": [datetime(2024, 3, 29, 6, tzinfo=UTC)],
        }
    )

    result = inspect_global_session_visibility(
        frame,
        a_share_open=datetime(2024, 3, 29, 1, 30, tzinfo=UTC),
        a_share_close=datetime(2024, 3, 29, 7, tzinfo=UTC),
    )

    assert result == (
        {
            "source_ticker": "N225",
            "timezone": "Asia/Tokyo",
            "event_time": "2024-03-29T06:00:00+00:00",
            "visible_at_a_share_open": False,
            "visible_at_a_share_close": True,
        },
    )
