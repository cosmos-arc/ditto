"""Union coverage semantics of field-level snapshot readiness (assess path)."""

from datetime import UTC, date, datetime

import pytest
from ditto_application.exceptions import AppQueryError
from ditto_application.queries.snapshot_readiness import (
    FieldRequirement,
    SnapshotReadinessQuery,
    SnapshotReadinessRequest,
)
from ditto_data.catalog.contracts import DataAssetRef
from ditto_data.catalog.source_snapshot import (
    ProviderSnapshot,
    ProviderSnapshotDraft,
)
from ditto_data.ingestion.partition_state import (
    PartitionCheckpoint,
    PartitionLifecycleEvent,
    PartitionLifecycleStatus,
)

_OBSERVED = datetime(2026, 10, 19, tzinfo=UTC)


class _SnapshotReader:
    """In-memory provider snapshot identity lookup."""

    def __init__(self, *snapshots: ProviderSnapshot) -> None:
        self._snapshots = {item.snapshot_id: item for item in snapshots}

    def get_snapshot(self, snapshot_id: str) -> ProviderSnapshot | None:
        return self._snapshots.get(snapshot_id)

    def get_observed_at(self, snapshot_id: str) -> datetime | None:
        return None

    def get_predecessor(self, snapshot_id: str) -> str | None:
        return None

    def list_snapshots(
        self,
        *,
        dataset_id: str | None = None,
        source: str | None = None,
        canonical_asset: DataAssetRef | None = None,
    ) -> tuple[ProviderSnapshot, ...]:
        return tuple(
            item
            for item in self._snapshots.values()
            if dataset_id is None or item.dataset_id == dataset_id
        )


class _LifecycleReader:
    """In-memory partition checkpoints for completion and hole claims."""

    def __init__(self, *checkpoints: PartitionCheckpoint) -> None:
        self._checkpoints = checkpoints

    def _list(
        self, complete: bool, *, dataset_id: str | None
    ) -> tuple[PartitionCheckpoint, ...]:
        return tuple(
            item
            for item in self._checkpoints
            if (item.status is PartitionLifecycleStatus.COMPLETE) is complete
            and (dataset_id is None or item.dataset_id == dataset_id)
        )

    def list_complete(
        self, *, dataset_id: str | None = None, source: str | None = None
    ) -> tuple[PartitionCheckpoint, ...]:
        return self._list(True, dataset_id=dataset_id)

    def list_incomplete(
        self, *, dataset_id: str | None = None, source: str | None = None
    ) -> tuple[PartitionCheckpoint, ...]:
        return self._list(False, dataset_id=dataset_id)

    def get_latest_checkpoint(self, chunk_id: str) -> PartitionCheckpoint | None:
        return next(
            (item for item in self._checkpoints if item.chunk_id == chunk_id), None
        )

    def get_checkpoint(self, chunk_id: str) -> PartitionCheckpoint | None:
        return self.get_latest_checkpoint(chunk_id)

    def list_events(self, chunk_id: str) -> tuple[PartitionLifecycleEvent, ...]:
        return ()


def _block(
    chunk_id: str,
    start: str,
    end: str,
    *,
    dataset_id: str = "stock_daily",
    status: PartitionLifecycleStatus = PartitionLifecycleStatus.COMPLETE,
) -> tuple[ProviderSnapshot, PartitionCheckpoint]:
    """One retained snapshot with lifecycle evidence matching its interval."""
    checksum = f"sha256:{chunk_id}"
    snapshot = ProviderSnapshot.create(
        ProviderSnapshotDraft(
            dataset_id=dataset_id,
            source="tushare",
            request_start=start,
            request_end=end,
            schema_version=f"market.{dataset_id}.v1",
            checksum=checksum,
            canonical_asset=DataAssetRef(dataset_id, "market"),
            request_parameters_hash=f"sha256:request:{chunk_id}",
            response_metadata=(),
            row_count=1,
            payload_uri=f"evidence://retained/{chunk_id}",
            payload_retained=True,
            created_at=_OBSERVED,
        )
    )
    payload_id = (
        f"payload:{checksum}:{chunk_id}:{snapshot.snapshot_id}"
        if status is PartitionLifecycleStatus.COMPLETE
        else None
    )
    checkpoint = PartitionCheckpoint(
        chunk_id=chunk_id,
        dataset_id=dataset_id,
        source="tushare",
        request_start=start,
        request_end=end,
        status=status,
        payload_id=payload_id,
        complete_evidence_id=(
            snapshot.snapshot_id
            if status is PartitionLifecycleStatus.COMPLETE
            else None
        ),
        error_code=None,
        updated_at=_OBSERVED,
    )
    return snapshot, checkpoint


def _query(
    *blocks: tuple[ProviderSnapshot, PartitionCheckpoint],
) -> SnapshotReadinessQuery:
    snapshots, checkpoints = zip(*blocks, strict=True)
    return SnapshotReadinessQuery(
        _SnapshotReader(*snapshots), _LifecycleReader(*checkpoints)
    )


def _patchwork() -> tuple[tuple[ProviderSnapshot, PartitionCheckpoint], ...]:
    """Backfilled shape: month block, week block, single day, weekend gaps."""
    return (
        _block("july", "2026-07-01", "2026-07-31"),
        _block("august-week", "2026-08-03", "2026-08-07"),
        _block("august-monday", "2026-08-10", "2026-08-10"),
    )


def _request(
    blocks, required_from: date, required_to: date
) -> SnapshotReadinessRequest:
    return SnapshotReadinessRequest(
        fields=tuple(
            FieldRequirement(
                snapshot.dataset_id, "close", snapshot.snapshot_id, "instruments.close"
            )
            for snapshot, _ in blocks
        ),
        required_from=required_from,
        required_to=required_to,
    )


def test_stitched_blocks_cover_multi_day_window_by_union():
    blocks = _patchwork()
    report = _query(*blocks).assess(
        _request(blocks, date(2026, 7, 1), date(2026, 8, 10))
    )
    assert report.ready
    assert all(item.reason_codes == () for item in report.fields)


def test_union_edge_gap_stays_fail_closed():
    blocks = _patchwork()
    # The mid-August week was never ingested: the window end sits outside
    # the union.
    report = _query(*blocks).assess(
        _request(blocks, date(2026, 7, 1), date(2026, 8, 14))
    )
    assert not report.ready
    assert all(
        item.reason_codes == ("SNAPSHOT_COVERAGE_MISSING",) for item in report.fields
    )


def test_chunk_claimed_hole_inside_window_fails_closed():
    july = _block("july-half", "2026-07-01", "2026-07-15")
    august = _block("august", "2026-08-01", "2026-08-31")
    # Late July was requested but ingestion never completed: the calendar gap
    # between the declared blocks is a real hole, not a non-trading span.
    stuck = _block(
        "july-tail",
        "2026-07-16",
        "2026-07-31",
        status=PartitionLifecycleStatus.PAYLOAD_COMMITTED,
    )
    blocks = (july, august)
    report = _query(july, august, stuck).assess(
        _request(blocks, date(2026, 7, 1), date(2026, 8, 31))
    )
    assert not report.ready
    assert all(
        item.reason_codes == ("SNAPSHOT_COVERAGE_MISSING",) for item in report.fields
    )


def test_whole_snapshot_path_keeps_single_snapshot_containment():
    blocks = _patchwork()
    query = _query(*blocks)
    august = blocks[1][0]
    # The same window the union serves is beyond one snapshot's own interval.
    assert query.snapshot_reasons(
        "stock_daily", august.snapshot_id, date(2026, 7, 1), date(2026, 9, 1)
    ) == ("SNAPSHOT_COVERAGE_MISSING",)
    assert (
        query.snapshot_reasons(
            "stock_daily", august.snapshot_id, date(2026, 8, 3), date(2026, 8, 7)
        )
        == ()
    )


def test_whole_snapshot_path_rejects_reversed_interval():
    blocks = _patchwork()
    query = _query(*blocks)
    with pytest.raises(AppQueryError, match="reversed"):
        query.snapshot_reasons(
            "stock_daily",
            blocks[0][0].snapshot_id,
            date(2026, 8, 1),
            date(2026, 7, 1),
        )


def test_knowledge_date_dataset_stays_exempt_from_coverage():
    roster = _block("roster", "2026-07-01", "2026-07-01", dataset_id="stock_basic")
    query = _query(roster)
    report = query.assess(
        SnapshotReadinessRequest(
            fields=(
                FieldRequirement(
                    "stock_basic",
                    "list_status",
                    roster[0].snapshot_id,
                    "instruments.listing_days",
                ),
            ),
            required_from=date(2026, 8, 1),
            required_to=date(2026, 8, 31),
        )
    )
    assert report.ready
    assert report.fields[0].reason_codes == ()
