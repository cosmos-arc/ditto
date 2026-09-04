"""Future-sentinel tests for the unified PIT query facade."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import polars as pl
import pytest
from ditto_data.query.contracts import DatasetSnapshot, PITQueryContext
from ditto_data.query.service import PITQueryService


def _snapshot() -> DatasetSnapshot:
    return DatasetSnapshot(
        dataset_id="macro_indicators",
        dataset_version="macro.macro_indicators.v1",
        source_snapshot_ids=("snapshot:fred:macro_indicators:sha256:abc",),
        created_at=datetime(2026, 8, 31, 8, tzinfo=UTC),
    )


def _context(snapshot: DatasetSnapshot | None = None) -> PITQueryContext:
    return PITQueryContext(
        as_of=datetime(2026, 8, 31, 9, tzinfo=UTC),
        knowledge_cutoff=datetime(2026, 8, 31, 9, tzinfo=UTC),
        publication_cutoff=datetime(2026, 8, 31, 8, 30, tzinfo=UTC),
        source_snapshots=((snapshot or _snapshot()),),
    )


@dataclass
class _Reader:
    frame: pl.DataFrame
    calls: list[DatasetSnapshot] = field(default_factory=list)

    def read_dataset(self, snapshot: DatasetSnapshot) -> pl.DataFrame:
        self.calls.append(snapshot)
        return self.frame


@pytest.mark.pit
def test_future_sentinel_is_invisible_and_query_is_snapshot_bound() -> None:
    snapshot = _snapshot()
    reader = _Reader(
        pl.DataFrame(
            {
                "indicator": ["visible", "future"],
                "event_time": [
                    datetime(2026, 8, 30, tzinfo=UTC),
                    datetime(2026, 8, 30, tzinfo=UTC),
                ],
                "published_at": [
                    datetime(2026, 8, 31, 8, tzinfo=UTC),
                    datetime(2026, 9, 1, tzinfo=UTC),
                ],
                "available_at": [
                    datetime(2026, 8, 31, 8, 15, tzinfo=UTC),
                    datetime(2026, 9, 1, 0, tzinfo=UTC),
                ],
                "source_snapshot_id": [
                    snapshot.source_snapshot_ids[0],
                    snapshot.source_snapshot_ids[0],
                ],
                "dataset_version": [
                    snapshot.dataset_version,
                    snapshot.dataset_version,
                ],
            }
        )
    )

    result = PITQueryService(reader).query(
        dataset_id="macro_indicators",
        context=_context(snapshot),
    )

    assert result["indicator"].to_list() == ["visible"]
    assert reader.calls == [snapshot]


@pytest.mark.pit
def test_timezone_boundaries_compare_as_the_same_utc_instant() -> None:
    snapshot = _snapshot()
    reader = _Reader(
        pl.DataFrame(
            {
                "indicator": ["visible", "future"],
                "event_time": [
                    datetime(2026, 8, 31, 7, 59, tzinfo=UTC),
                    datetime(2026, 8, 31, 8, 1, tzinfo=UTC),
                ],
                "published_at": [
                    datetime(2026, 8, 31, 7, 30, tzinfo=UTC),
                    datetime(2026, 8, 31, 7, 30, tzinfo=UTC),
                ],
                "available_at": [
                    datetime(2026, 8, 31, 7, 30, tzinfo=UTC),
                    datetime(2026, 8, 31, 7, 30, tzinfo=UTC),
                ],
                "source_snapshot_id": [
                    snapshot.source_snapshot_ids[0],
                    snapshot.source_snapshot_ids[0],
                ],
                "dataset_version": [
                    snapshot.dataset_version,
                    snapshot.dataset_version,
                ],
            }
        )
    )
    shanghai = ZoneInfo("Asia/Shanghai")
    context = PITQueryContext(
        as_of=datetime(2026, 8, 31, 16, tzinfo=shanghai),
        knowledge_cutoff=datetime(2026, 8, 31, 16, tzinfo=shanghai),
        publication_cutoff=datetime(2026, 8, 31, 16, tzinfo=shanghai),
        source_snapshots=(snapshot,),
    )

    result = PITQueryService(reader).query(
        dataset_id=snapshot.dataset_id,
        context=context,
    )

    assert result["indicator"].to_list() == ["visible"]


@pytest.mark.pit
def test_query_fails_closed_before_io_without_exact_dataset_snapshot() -> None:
    reader = _Reader(pl.DataFrame())

    with pytest.raises(ValueError, match="source snapshot"):
        PITQueryService(reader).query(
            dataset_id="stock_daily",
            context=_context(),
        )

    assert reader.calls == []


@pytest.mark.pit
@pytest.mark.parametrize(
    "missing_column",
    [
        "event_time",
        "published_at",
        "available_at",
        "source_snapshot_id",
        "dataset_version",
    ],
)
def test_query_rejects_rows_without_required_time_and_lineage_fields(
    missing_column: str,
) -> None:
    snapshot = _snapshot()
    payload = {
        "event_time": [datetime(2026, 8, 30, tzinfo=UTC)],
        "published_at": [datetime(2026, 8, 31, 8, tzinfo=UTC)],
        "available_at": [datetime(2026, 8, 31, 8, 15, tzinfo=UTC)],
        "source_snapshot_id": [snapshot.source_snapshot_ids[0]],
        "dataset_version": [snapshot.dataset_version],
    }
    payload.pop(missing_column)

    with pytest.raises(ValueError, match="required PIT columns"):
        PITQueryService(_Reader(pl.DataFrame(payload))).query(
            dataset_id=snapshot.dataset_id,
            context=_context(snapshot),
        )


@pytest.mark.pit
def test_query_rejects_snapshot_or_version_drift() -> None:
    snapshot = _snapshot()
    reader = _Reader(
        pl.DataFrame(
            {
                "event_time": [datetime(2026, 8, 30, tzinfo=UTC)],
                "published_at": [datetime(2026, 8, 31, 8, tzinfo=UTC)],
                "available_at": [datetime(2026, 8, 31, 8, 15, tzinfo=UTC)],
                "source_snapshot_id": ["snapshot:fred:macro_indicators:sha256:other"],
                "dataset_version": ["macro.macro_indicators.v2"],
            }
        )
    )

    with pytest.raises(ValueError, match="snapshot or version drift"):
        PITQueryService(reader).query(
            dataset_id=snapshot.dataset_id,
            context=_context(snapshot),
        )


def test_context_rejects_naive_or_inverted_cutoffs() -> None:
    snapshot = _snapshot()
    with pytest.raises(ValueError, match="timezone-aware"):
        PITQueryContext(
            as_of=datetime(2026, 8, 31, 9),
            knowledge_cutoff=datetime(2026, 8, 31, 9, tzinfo=UTC),
            publication_cutoff=datetime(2026, 8, 31, 8, tzinfo=UTC),
            source_snapshots=(snapshot,),
        )

    with pytest.raises(ValueError, match="publication_cutoff"):
        PITQueryContext(
            as_of=datetime(2026, 8, 31, 9, tzinfo=UTC),
            knowledge_cutoff=datetime(2026, 8, 31, 8, tzinfo=UTC),
            publication_cutoff=datetime(2026, 8, 31, 8, 1, tzinfo=UTC),
            source_snapshots=(snapshot,),
        )
