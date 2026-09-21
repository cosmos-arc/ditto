"""Unit tests for snapshot-bound checkpoint matching."""

from __future__ import annotations

from datetime import UTC, datetime

from ditto_data.catalog.contracts import DataAssetRef
from ditto_data.catalog.snapshot_completion import checkpoint_matches_snapshot
from ditto_data.catalog.source_snapshot import ProviderSnapshot, ProviderSnapshotDraft
from ditto_data.ingestion.partition_state import (
    PartitionCheckpoint,
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
            license_record_id="license:tushare:v1",
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
        last_successful_stage=PartitionLifecycleStatus.PAYLOAD_COMMITTED,
        attempt=1,
        retry_budget=3,
        payload_id=payload_id,
        catalog_asset_id=None,
        lineage_run_id=None,
        ingestion_log_id=None,
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
