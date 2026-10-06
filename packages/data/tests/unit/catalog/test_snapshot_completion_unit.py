"""Unit tests for snapshot-bound checkpoint matching."""

from __future__ import annotations

from datetime import UTC, datetime

from ditto_data.catalog.contracts import DataAssetRef
from ditto_data.catalog.snapshot_completion import (
    checkpoint_matches_snapshot,
    snapshot_completed,
)
from ditto_data.catalog.source_snapshot import ProviderSnapshot, ProviderSnapshotDraft
from ditto_data.ingestion.partition_state import (
    PartitionCheckpoint,
    PartitionLifecycleEvent,
    PartitionLifecycleStatus,
)


def _snapshot(schema_version: str) -> ProviderSnapshot:
    return ProviderSnapshot.create(
        ProviderSnapshotDraft(
            dataset_id="stock_daily",
            source="tushare",
            request_start="2026-06-01",
            request_end="2026-06-01",
            schema_version=schema_version,
            checksum="sha256:same-bytes",
            canonical_asset=DataAssetRef(
                dataset_id="stock_daily",
                namespace="market",
                partition_keys=("trade_date=2026-06-01",),
            ),
            request_parameters_hash="request:tushare",
            response_metadata=(),
            row_count=2,
            payload_uri="provider_payloads/tushare/stock_daily/same.parquet",
            payload_retained=True,
            created_at=datetime(2026, 6, 1, 10, 0, tzinfo=UTC),
        )
    )


def _checkpoint(payload_id: str | None) -> PartitionCheckpoint:
    return PartitionCheckpoint(
        chunk_id="chunk:tushare:stock_daily:2026-06-01",
        dataset_id="stock_daily",
        source="tushare",
        request_start="2026-06-01",
        request_end="2026-06-01",
        status=PartitionLifecycleStatus.PAYLOAD_COMMITTED,
        payload_id=payload_id,
        complete_evidence_id=None,
        error_code=None,
        updated_at=datetime(2026, 6, 1, 10, 5, tzinfo=UTC),
    )


class TestCheckpointMatchesSnapshot:
    """Payload-committed evidence must pin the exact snapshot identity."""

    def test_same_checksum_but_other_snapshot_identity_does_not_match(self) -> None:
        v1 = _snapshot("market.stock_daily.v1")
        v2 = _snapshot("market.stock_daily.v2")
        checkpoint = _checkpoint(
            f"payload:{v1.checksum}:stock_daily/2026:{v1.snapshot_id}"
        )

        assert checkpoint_matches_snapshot(checkpoint, v1)
        assert not checkpoint_matches_snapshot(checkpoint, v2)

    def test_legacy_payload_evidence_without_snapshot_identity_does_not_match(
        self,
    ) -> None:
        snapshot = _snapshot("market.stock_daily.v1")
        checkpoint = _checkpoint(f"payload:{snapshot.checksum}:stock_daily/2026")

        assert not checkpoint_matches_snapshot(checkpoint, snapshot)

    def test_intent_evidence_still_matches_same_bytes(self) -> None:
        snapshot = _snapshot("market.stock_daily.v1")
        checkpoint = _checkpoint(f"intent:{snapshot.checksum}")

        assert checkpoint_matches_snapshot(checkpoint, snapshot)


class _Lifecycle:
    """Minimal completion reader over synthetic checkpoints."""

    def get_latest_checkpoint(self, chunk_id: str) -> PartitionCheckpoint | None:
        raise AssertionError(f"completion checks must not read latest: {chunk_id}")

    def get_checkpoint(self, chunk_id: str) -> PartitionCheckpoint | None:
        raise AssertionError(f"completion checks must not read checkpoints: {chunk_id}")

    def list_incomplete(
        self,
        *,
        dataset_id: str | None = None,
        source: str | None = None,
    ) -> tuple[PartitionCheckpoint, ...]:
        raise AssertionError("completion checks must not list incomplete chunks")

    def list_complete(
        self,
        *,
        dataset_id: str | None = None,
        source: str | None = None,
    ) -> tuple[PartitionCheckpoint, ...]:
        return tuple(
            checkpoint
            for checkpoint in self._checkpoints
            if checkpoint.dataset_id == dataset_id
            and checkpoint.status is PartitionLifecycleStatus.COMPLETE
        )

    def list_events(self, chunk_id: str) -> tuple[PartitionLifecycleEvent, ...]:
        raise AssertionError(f"completion checks must not read events: {chunk_id}")

    def __init__(self, *checkpoints: PartitionCheckpoint) -> None:
        self._checkpoints = checkpoints


class TestSnapshotCompleted:
    """COMPLETE 行必须以 complete_evidence_id 绑定精确快照身份。"""

    def _complete(self, snapshot: ProviderSnapshot, evidence_id: str | None):
        return PartitionCheckpoint(
            chunk_id="chunk:tushare:stock_daily:2026-06-01",
            dataset_id="stock_daily",
            source="tushare",
            request_start="2026-06-01",
            request_end="2026-06-01",
            status=PartitionLifecycleStatus.COMPLETE,
            payload_id=f"payload:{snapshot.checksum}:stock_daily/2026:{snapshot.snapshot_id}",
            complete_evidence_id=evidence_id,
            error_code=None,
            updated_at=datetime(2026, 6, 1, 10, 6, tzinfo=UTC),
        )

    def test_complete_evidence_binding_attests_snapshot(self) -> None:
        snapshot = _snapshot("market.stock_daily.v1")
        lifecycle = _Lifecycle(
            self._complete(snapshot, evidence_id=snapshot.snapshot_id)
        )

        assert snapshot_completed(snapshot, lifecycle)

    def test_legacy_complete_without_evidence_stays_incomplete(self) -> None:
        snapshot = _snapshot("market.stock_daily.v1")
        lifecycle = _Lifecycle(self._complete(snapshot, evidence_id=None))

        assert not snapshot_completed(snapshot, lifecycle)

    def test_complete_bound_to_other_snapshot_stays_incomplete(self) -> None:
        v1 = _snapshot("market.stock_daily.v1")
        v2 = _snapshot("market.stock_daily.v2")
        lifecycle = _Lifecycle(self._complete(v1, evidence_id=v1.snapshot_id))

        assert snapshot_completed(v1, lifecycle)
        assert not snapshot_completed(v2, lifecycle)
