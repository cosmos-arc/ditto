"""Provider-specific source snapshot persistence tests."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest
from ditto_data.catalog.contracts import DataAssetRef
from ditto_data.catalog.source_snapshot import (
    ProviderSnapshot,
    ProviderSnapshotDraft,
    ProviderSnapshotReader,
    ProviderSnapshotWriter,
)
from ditto_data.catalog.source_snapshot_store import SQLiteProviderSnapshotStore
from ditto_platform.foundation import SQLiteClient, SQLitePool


def _client(db_path: Path) -> tuple[SQLiteClient, SQLitePool]:
    pool = SQLitePool(str(db_path))
    return SQLiteClient(pool), pool


def _snapshot(source: str, checksum: str) -> ProviderSnapshot:
    return ProviderSnapshot.create(
        ProviderSnapshotDraft(
            dataset_id="stock_daily",
            source=source,
            request_start="2026-06-01",
            request_end="2026-06-01",
            schema_version="market.stock_daily.v1",
            checksum=checksum,
            canonical_asset=DataAssetRef(
                dataset_id="stock_daily",
                namespace="market",
                partition_keys=("trade_date=2026-06-01",),
            ),
            request_parameters_hash=f"request:{source}",
            response_metadata=(("provider_request_id", f"request-{source}"),),
            license_record_id=f"license:{source}:v1",
            row_count=2,
            payload_uri=f"source_snapshot/{source}/stock_daily/2026-06-01",
            payload_retained=True,
            created_at=datetime(2026, 6, 1, 10, 0, tzinfo=UTC),
        )
    )


class TestSQLiteProviderSnapshotStore:
    def test_preserves_multiple_sources_for_same_canonical_partition(
        self, tmp_path: Path
    ) -> None:
        client, pool = _client(tmp_path / "catalog.sqlite")
        store = SQLiteProviderSnapshotStore(client)
        tushare = _snapshot("tushare", "sha256:tushare")
        tdx = _snapshot("local_tdx", "sha256:tdx")

        try:
            store.append_snapshot(tushare)
            store.append_snapshot(tdx)

            assert store.get_snapshot(tushare.snapshot_id) == tushare
            assert store.get_snapshot(tdx.snapshot_id) == tdx
            assert store.list_snapshots(canonical_asset=tushare.canonical_asset) == (
                tdx,
                tushare,
            )
        finally:
            pool.close()

    def test_identical_append_is_idempotent(self, tmp_path: Path) -> None:
        client, pool = _client(tmp_path / "catalog.sqlite")
        store = SQLiteProviderSnapshotStore(client)
        snapshot = _snapshot("tushare", "sha256:tushare")

        try:
            store.append_snapshot(snapshot)
            store.append_snapshot(snapshot)

            assert store.list_snapshots(dataset_id="stock_daily") == (snapshot,)
        finally:
            pool.close()

    def test_rejects_mutation_of_existing_snapshot(self, tmp_path: Path) -> None:
        client, pool = _client(tmp_path / "catalog.sqlite")
        store = SQLiteProviderSnapshotStore(client)
        snapshot = _snapshot("tushare", "sha256:tushare")
        mutated = replace(
            snapshot,
            response_metadata=(("provider_request_id", "other"),),
        )

        try:
            store.append_snapshot(snapshot)

            with pytest.raises(ValueError, match="immutable provider snapshot"):
                store.append_snapshot(mutated)
        finally:
            pool.close()

    def test_survives_reopened_connection(self, tmp_path: Path) -> None:
        db_path = tmp_path / "catalog.sqlite"
        snapshot = _snapshot("tushare", "sha256:tushare")
        writer_client, writer_pool = _client(db_path)
        try:
            SQLiteProviderSnapshotStore(writer_client).append_snapshot(snapshot)
        finally:
            writer_pool.close()

        reader_client, reader_pool = _client(db_path)
        try:
            store = SQLiteProviderSnapshotStore(reader_client)
            assert store.get_snapshot(snapshot.snapshot_id) == snapshot
            assert isinstance(store, ProviderSnapshotReader)
            assert isinstance(store, ProviderSnapshotWriter)
        finally:
            reader_pool.close()


class TestProviderSnapshotIdentity:
    def test_identity_changes_with_required_provider_dimensions(self) -> None:
        baseline = _snapshot("tushare", "sha256:v1")

        assert _snapshot("local_tdx", "sha256:v1").snapshot_id != baseline.snapshot_id
        assert _snapshot("tushare", "sha256:v2").snapshot_id != baseline.snapshot_id
        assert (
            replace(baseline, request_end="2026-06-02").expected_snapshot_id()
            != baseline.snapshot_id
        )

    def test_rejects_secret_like_response_metadata(self) -> None:
        with pytest.raises(ValueError, match="secret"):
            ProviderSnapshot.create(
                ProviderSnapshotDraft(
                    dataset_id="stock_daily",
                    source="tushare",
                    request_start="2026-06-01",
                    request_end="2026-06-01",
                    schema_version="market.stock_daily.v1",
                    checksum="sha256:payload",
                    canonical_asset=DataAssetRef(
                        dataset_id="stock_daily",
                        namespace="market",
                        partition_keys=("trade_date=2026-06-01",),
                    ),
                    request_parameters_hash="request:tushare",
                    response_metadata=(("api_token", "should-not-be-persisted"),),
                    license_record_id="license:tushare:v1",
                    row_count=2,
                    payload_uri=None,
                    payload_retained=False,
                    created_at=datetime(2026, 6, 1, 10, 0, tzinfo=UTC),
                )
            )


class TestObservationBackfill:
    def test_reingesting_legacy_snapshot_records_observation_at_reingestion_time(
        self, tmp_path: Path
    ) -> None:
        client, pool = _client(tmp_path / "catalog.sqlite")
        reingested_at = datetime(2026, 9, 21, 12, 0, tzinfo=UTC)
        store = SQLiteProviderSnapshotStore(client, now=lambda: reingested_at)
        snapshot = _snapshot("tushare", "sha256:tushare")

        try:
            store.append_snapshot(snapshot)
            # A store upgraded before the observation ledger existed has rows
            # without observations.
            client.execute(
                "DELETE FROM provider_snapshot_observations WHERE snapshot_id = ?",
                [snapshot.snapshot_id],
            )
            client.commit()
            assert store.get_observed_at(snapshot.snapshot_id) is None

            store.append_snapshot(snapshot)

            observed = store.get_observed_at(snapshot.snapshot_id)
            assert observed == reingested_at
            assert store.get_predecessor(snapshot.snapshot_id) is None
        finally:
            pool.close()


class TestReobservationOrdering:
    def test_reobservations_preserve_intermediate_events(self, tmp_path: Path) -> None:
        """A→B→A→A keeps both re-observations for cutoff replay."""
        client, pool = _client(tmp_path / "catalog.sqlite")
        store = SQLiteProviderSnapshotStore(client)
        original = _snapshot("tushare", "sha256:open")
        closed = replace(
            _snapshot("tushare", "sha256:closed"),
            created_at=datetime(2026, 6, 2, 10, 0, tzinfo=UTC),
        )
        reopened = replace(
            _snapshot("tushare", "sha256:open"),
            created_at=datetime(2026, 6, 3, 10, 0, tzinfo=UTC),
        )
        observed_again = replace(
            reopened, created_at=datetime(2026, 6, 5, 10, 0, tzinfo=UTC)
        )

        try:
            store.append_snapshot(original)
            store.append_snapshot(closed)
            store.append_snapshot(reopened)
            store.append_snapshot(observed_again)

            stored = store.get_snapshot(original.snapshot_id)
            assert stored is not None
            # 首次可见时间不可变；重观察作为事件追加，历史完整保留。
            assert stored.created_at == original.created_at
            assert stored.observations == (
                reopened.created_at,
                observed_again.created_at,
            )
        finally:
            pool.close()

    def test_upgrade_keeps_last_recorded_reobservation(self, tmp_path: Path) -> None:
        client, pool = _client(tmp_path / "catalog.sqlite")
        snapshot = _snapshot("tushare", "sha256:open")
        observed_at = datetime(2026, 6, 3, 10, tzinfo=UTC)
        try:
            SQLiteProviderSnapshotStore(client).append_snapshot(snapshot)
            client.execute(
                "ALTER TABLE provider_snapshots ADD COLUMN last_observed_at TEXT"
            )
            client.execute(
                "UPDATE provider_snapshots SET last_observed_at = ? "
                "WHERE snapshot_id = ?",
                [observed_at.isoformat(), snapshot.snapshot_id],
            )
            client.commit()

            upgraded = SQLiteProviderSnapshotStore(client)
            assert upgraded.get_snapshot(snapshot.snapshot_id) == replace(
                snapshot, observations=(observed_at,)
            )
        finally:
            pool.close()


class TestSchemaFingerprintBackfill:
    def test_reingesting_legacy_snapshot_backfills_fingerprint(
        self, tmp_path: Path
    ) -> None:
        import polars as pl
        from ditto_data.catalog.provider_payload import schema_fingerprint

        client, pool = _client(tmp_path / "catalog.sqlite")
        store = SQLiteProviderSnapshotStore(client)
        legacy = _snapshot("tushare", "sha256:tushare")
        assert legacy.schema_fingerprint is None

        try:
            store.append_snapshot(legacy)
            frame = pl.DataFrame({"instrument_id": [1], "close": [10.5]})
            upgraded = replace(legacy, schema_fingerprint=schema_fingerprint(frame))

            store.append_snapshot(upgraded)

            assert store.get_snapshot(legacy.snapshot_id) == upgraded
        finally:
            pool.close()
