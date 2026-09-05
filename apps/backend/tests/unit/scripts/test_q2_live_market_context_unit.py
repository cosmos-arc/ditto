"""Unit contracts for the Q2 live MarketContext acceptance driver."""

from __future__ import annotations

from datetime import UTC, date, datetime

import polars as pl
import pytest
from ditto_apps.scripts.q2_live_market_context import (
    inspect_global_session_visibility,
    select_interval_snapshot_ids,
)
from ditto_data.catalog.contracts import DataAssetRef
from ditto_data.catalog.source_snapshot import ProviderSnapshot


def _snapshot(
    *,
    snapshot_id: str,
    request_start: str,
    request_end: str,
    payload_uri: str,
) -> ProviderSnapshot:
    return ProviderSnapshot(
        snapshot_id=snapshot_id,
        dataset_id="index_daily",
        source="tushare",
        request_start=request_start,
        request_end=request_end,
        schema_version="1",
        checksum=f"sha256:{snapshot_id}",
        canonical_asset=DataAssetRef(
            dataset_id="index_daily",
            namespace="market/index",
        ),
        request_parameters_hash=f"request:{snapshot_id}",
        response_metadata=(),
        license_record_id="license:tushare",
        row_count=1,
        payload_uri=payload_uri,
        payload_retained=True,
        created_at=datetime(2024, 3, 29, tzinfo=UTC),
    )


@pytest.mark.unit
def test_select_interval_snapshot_ids_rejects_point_snapshot_for_range() -> None:
    snapshots = (
        _snapshot(
            snapshot_id="snapshot-point",
            request_start="2024-03-29",
            request_end="2024-03-29",
            payload_uri="point.parquet",
        ),
        _snapshot(
            snapshot_id="snapshot-range-b",
            request_start="2024-02-01",
            request_end="2024-03-29",
            payload_uri="range-b.parquet",
        ),
        _snapshot(
            snapshot_id="snapshot-range-a",
            request_start="2024-02-01",
            request_end="2024-03-29",
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
