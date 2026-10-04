"""Fail-closed ingestion evidence saga tests."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from ditto_application.processes.ingestion.evidence_commit import (
    EvidenceCommitPorts,
    EvidenceCommitRequest,
    IngestionEvidenceCommitter,
    _payload_evidence_id,
)
from ditto_data.catalog import (
    DataAssetRef,
    DataCatalogEntry,
    DataSchemaFingerprint,
)
from ditto_data.catalog.snapshot_completion import snapshot_completed
from ditto_data.catalog.source_snapshot import ProviderSnapshot, ProviderSnapshotDraft
from ditto_data.ingestion.partition_state import (
    PartitionCheckpoint,
    PartitionLifecycleStatus,
)
from ditto_data.ingestion.partition_state_store import SQLitePartitionLifecycleStore
from ditto_data.models.ingestion import IngestionLog, IngestionStatus
from ditto_platform.foundation import SQLiteClient, SQLitePool


class _Recorder:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.values: list[object] = []

    def append_snapshot(self, value: object) -> None:
        self._record(value)

    def upsert_asset(self, value: object) -> None:
        self._record(value)

    def save_log(self, value: object) -> object:
        self._record(value)
        return value

    def get_snapshot(self, snapshot_id: str) -> ProviderSnapshot | None:
        return next(
            (
                v
                for v in self.values
                if isinstance(v, ProviderSnapshot) and v.snapshot_id == snapshot_id
            ),
            None,
        )

    def list_snapshots(
        self,
        *,
        dataset_id: str | None = None,
        source: str | None = None,
        canonical_asset: DataAssetRef | None = None,
    ) -> tuple[ProviderSnapshot, ...]:
        return tuple(v for v in self.values if isinstance(v, ProviderSnapshot))

    def get_log(
        self, dataset: str, source: str, trade_date: str
    ) -> IngestionLog | None:
        return next(
            (
                v
                for v in self.values
                if isinstance(v, IngestionLog)
                and (v.dataset, v.source, v.trade_date) == (dataset, source, trade_date)
            ),
            None,
        )

    def _record(self, value: object) -> None:
        if self.fail:
            raise RuntimeError("injected durable evidence failure")
        self.values.append(value)


def _request(
    schema_version: str = "market.stock_daily.v1",
    checksum: str = "sha256:payload",
) -> EvidenceCommitRequest:
    now = datetime(2026, 7, 18, 8, 30, tzinfo=UTC)
    canonical_asset = DataAssetRef(dataset_id="stock_daily", namespace="market")
    snapshot = ProviderSnapshot.create(
        ProviderSnapshotDraft(
            dataset_id="stock_daily",
            source="tushare",
            request_start="2026-07-17",
            request_end="2026-07-17",
            schema_version=schema_version,
            checksum=checksum,
            canonical_asset=canonical_asset,
            request_parameters_hash="sha256:request",
            response_metadata=(
                ("canonical_checksum", checksum),
                ("canonical_row_count", "1"),
                ("snapshot_layer", "normalized_provider_payload"),
            ),
            row_count=1,
            payload_uri="stock_daily/2026/07/17.parquet",
            payload_retained=True,
            created_at=now,
        )
    )
    catalog_entry = DataCatalogEntry(
        asset=canonical_asset,
        storage_uri="stock_daily/2026/07/17.parquet",
        schema=DataSchemaFingerprint(
            schema_hash="schema:sha256:stock-daily",
            row_count=1,
            created_at=now,
            schema_version="market.stock_daily.v1",
            columns=("instrument_id", "trade_date", "close"),
        ),
        source="tushare",
        freshness_at=now,
        source_snapshot_id=snapshot.snapshot_id,
    )
    return EvidenceCommitRequest(
        chunk_id="chunk:tushare:stock_daily:2026-07-17",
        dataset_id="stock_daily",
        source="tushare",
        request_start="2026-07-17",
        request_end="2026-07-17",
        provider_snapshot=snapshot,
        catalog_entry=catalog_entry,
        # Canonical output is explicitly bound in the retained snapshot metadata.
        success_log=IngestionLog(
            dataset="stock_daily",
            source="tushare",
            trade_date="2026-07-17",
            status=IngestionStatus.SUCCESS,
            checksum=checksum,
            rows=1,
        ),
    )


def _store(tmp_path: Path) -> tuple[SQLitePartitionLifecycleStore, SQLitePool]:
    pool = SQLitePool(str(tmp_path / "runtime.sqlite"))
    return SQLitePartitionLifecycleStore(SQLiteClient(pool)), pool


def _ports(lifecycle, snapshot, catalog, logs) -> EvidenceCommitPorts:
    return EvidenceCommitPorts(
        lifecycle_reader=lifecycle,
        lifecycle_writer=lifecycle,
        snapshot_writer=snapshot,
        snapshot_reader=snapshot,
        catalog_writer=catalog,
        ingestion_log_store=logs,
    )


def _planned(request: EvidenceCommitRequest, *, payload_id: str | None = None):
    return PartitionCheckpoint(
        chunk_id=request.chunk_id,
        dataset_id=request.dataset_id,
        source=request.source,
        request_start=request.request_start,
        request_end=request.request_end,
        status=PartitionLifecycleStatus.PLANNED,
        last_successful_stage=None,
        attempt=1,
        retry_budget=3,
        payload_id=payload_id,
        complete_evidence_id=None,
        error_code=None,
        updated_at=datetime(2026, 7, 18, 8, 40, tzinfo=UTC),
    )


@pytest.mark.unit
def test_evidence_commit_reaches_complete_only_after_all_durable_writes(
    tmp_path: Path,
) -> None:
    lifecycle, pool = _store(tmp_path)
    snapshot, catalog, logs = (_Recorder() for _ in range(3))
    committer = IngestionEvidenceCommitter(
        ports=_ports(lifecycle, snapshot, catalog, logs),
        now=lambda: datetime(2026, 7, 18, 9, 0, tzinfo=UTC),
    )

    try:
        outcome = committer.commit(_request())

        assert outcome.completed is True
        assert outcome.error_code is None
        checkpoint = lifecycle.get_checkpoint(outcome.chunk_id)
        assert checkpoint is not None
        assert checkpoint.status is PartitionLifecycleStatus.COMPLETE
        assert (
            checkpoint.complete_evidence_id == _request().provider_snapshot.snapshot_id
        )
        assert len(snapshot.values) == 1
        assert len(catalog.values) == 1
        assert len(logs.values) == 1
        # 三阶段状态机:PLANNED → PAYLOAD_COMMITTED → COMPLETE,无中间簿记阶段。
        assert [
            event.to_status for event in lifecycle.list_events(outcome.chunk_id)
        ] == [
            PartitionLifecycleStatus.PLANNED,
            PartitionLifecycleStatus.PAYLOAD_COMMITTED,
            PartitionLifecycleStatus.COMPLETE,
        ]
    finally:
        pool.close()


@pytest.mark.unit
@pytest.mark.parametrize(
    ("failing_port", "expected_status", "expected_error"),
    [
        ("snapshot", PartitionLifecycleStatus.ORPHAN_PAYLOAD, "SNAPSHOT_WRITE_FAILED"),
        ("catalog", PartitionLifecycleStatus.ORPHAN_PAYLOAD, "CATALOG_WRITE_FAILED"),
        ("logs", PartitionLifecycleStatus.CATALOG_ONLY, "SUCCESS_LOG_WRITE_FAILED"),
    ],
)
def test_evidence_commit_fails_closed_at_each_durable_boundary(
    tmp_path: Path,
    failing_port: str,
    expected_status: PartitionLifecycleStatus,
    expected_error: str,
) -> None:
    lifecycle, pool = _store(tmp_path)
    ports = {
        name: _Recorder(fail=name == failing_port)
        for name in ("snapshot", "catalog", "logs")
    }
    committer = IngestionEvidenceCommitter(
        ports=_ports(lifecycle, ports["snapshot"], ports["catalog"], ports["logs"]),
        now=lambda: datetime(2026, 7, 18, 9, 0, tzinfo=UTC),
    )

    try:
        outcome = committer.commit(_request())

        assert outcome.completed is False
        assert outcome.error_code == expected_error
        checkpoint = lifecycle.get_checkpoint(outcome.chunk_id)
        assert checkpoint is not None
        assert checkpoint.status is expected_status
        assert checkpoint.status is not PartitionLifecycleStatus.COMPLETE
    finally:
        pool.close()


@pytest.mark.unit
def test_reingest_legacy_completion_reattests_on_new_revision(
    tmp_path: Path,
) -> None:
    lifecycle, pool = _store(tmp_path)
    snapshot = _Recorder()
    catalog = _Recorder()
    logs = _Recorder()
    committer = IngestionEvidenceCommitter(
        ports=_ports(lifecycle, snapshot, catalog, logs),
        now=lambda: datetime(2026, 7, 18, 9, 0, tzinfo=UTC),
    )
    request = _request()

    try:
        lifecycle.plan_partition(_planned(request))
        lifecycle.advance_partition(
            request.chunk_id,
            PartitionLifecycleStatus.PAYLOAD_COMMITTED,
            occurred_at=datetime(2026, 7, 18, 8, 41, tzinfo=UTC),
            evidence_id=_payload_evidence_id(request),
        )
        lifecycle.advance_partition(
            request.chunk_id,
            PartitionLifecycleStatus.COMPLETE,
            occurred_at=datetime(2026, 7, 18, 8, 42, tzinfo=UTC),
            evidence_id=request.provider_snapshot.snapshot_id,
        )
        # Legacy completions predate snapshot-bound COMPLETE evidence:
        # 模拟升级前行,complete_evidence_id 为空。
        SQLiteClient(pool).execute(
            "UPDATE ingestion_partition_checkpoints SET complete_evidence_id = NULL "
            "WHERE chunk_id = ?",
            [request.chunk_id],
        )
        SQLiteClient(pool).commit()
        snapshot.values.append(request.provider_snapshot)
        logs.values.append(request.success_log)

        outcome = committer.commit(request)

        assert outcome.completed is True
        assert outcome.error_code is None
        assert outcome.chunk_id.startswith(f"{request.chunk_id}:revision:")
        base_checkpoint = lifecycle.get_checkpoint(request.chunk_id)
        assert base_checkpoint is not None
        assert base_checkpoint.status is PartitionLifecycleStatus.COMPLETE
        assert base_checkpoint.complete_evidence_id is None
        assert snapshot_completed(request.provider_snapshot, lifecycle)
        assert len(logs.values) == 1

        replay = committer.commit(request)

        assert replay.completed is True
        assert replay.chunk_id == outcome.chunk_id
        assert len(logs.values) == 1
    finally:
        pool.close()


@pytest.mark.unit
def test_schema_version_change_with_same_checksum_reattests_new_snapshot(
    tmp_path: Path,
) -> None:
    lifecycle, pool = _store(tmp_path)
    recorder = _Recorder()
    committer = IngestionEvidenceCommitter(
        ports=_ports(lifecycle, recorder, recorder, recorder),
        now=lambda: datetime(2026, 7, 18, 9, 0, tzinfo=UTC),
    )
    request_v1 = _request()
    request_v2 = _request(schema_version="market.stock_daily.v2")

    try:
        first = committer.commit(request_v1)

        assert first.completed is True
        assert first.chunk_id == request_v1.chunk_id
        assert snapshot_completed(request_v1.provider_snapshot, lifecycle)

        second = committer.commit(request_v2)

        assert second.completed is True
        assert second.chunk_id != request_v1.chunk_id
        assert second.chunk_id.startswith(f"{request_v1.chunk_id}:revision:")
        assert snapshot_completed(request_v2.provider_snapshot, lifecycle)
        assert snapshot_completed(request_v1.provider_snapshot, lifecycle)

        replay = committer.commit(request_v2)

        assert replay.completed is True
        assert replay.chunk_id == second.chunk_id
    finally:
        pool.close()


@pytest.mark.unit
def test_repair_resumes_after_payload_without_rewriting_payload(tmp_path: Path) -> None:
    lifecycle, pool = _store(tmp_path)
    snapshot = _Recorder()
    catalog = _Recorder(fail=True)
    logs = _Recorder()
    committer = IngestionEvidenceCommitter(
        ports=_ports(lifecycle, snapshot, catalog, logs),
        now=lambda: datetime(2026, 7, 18, 9, 0, tzinfo=UTC),
    )
    request = _request()

    try:
        failed = committer.commit(request)
        catalog.fail = False
        repaired = committer.commit(request)

        assert failed.completed is False
        assert repaired.completed is True
        checkpoint = lifecycle.get_checkpoint(request.chunk_id)
        assert checkpoint is not None
        assert checkpoint.attempt == 2
        payload_events = [
            event
            for event in lifecycle.list_events(request.chunk_id)
            if event.to_status is PartitionLifecycleStatus.PAYLOAD_COMMITTED
            and event.evidence_id is not None
        ]
        assert len(payload_events) == 1
        assert len(logs.values) == 1
    finally:
        pool.close()


@pytest.mark.unit
def test_schema_change_after_partial_attestation_forks_new_revision(
    tmp_path: Path,
) -> None:
    lifecycle, pool = _store(tmp_path)
    snapshot = _Recorder()
    catalog = _Recorder()
    logs = _Recorder()
    committer = IngestionEvidenceCommitter(
        ports=_ports(lifecycle, snapshot, catalog, logs),
        now=lambda: datetime(2026, 7, 18, 9, 0, tzinfo=UTC),
    )
    request_v1 = _request()
    request_v2 = _request(schema_version="market.stock_daily.v2")

    try:
        lifecycle.plan_partition(_planned(request_v1))
        lifecycle.advance_partition(
            request_v1.chunk_id,
            PartitionLifecycleStatus.PAYLOAD_COMMITTED,
            occurred_at=datetime(2026, 7, 18, 8, 41, tzinfo=UTC),
            evidence_id=_payload_evidence_id(request_v1),
        )

        forked = committer.commit(request_v2)

        assert forked.completed is True
        assert forked.chunk_id != request_v1.chunk_id
        assert forked.chunk_id.startswith(f"{request_v1.chunk_id}:revision:")
        assert any(
            item.snapshot_id == request_v2.provider_snapshot.snapshot_id
            for item in snapshot.values
        )
        assert snapshot_completed(request_v2.provider_snapshot, lifecycle)

        resumed = committer.commit(request_v1)

        assert resumed.completed is True
        assert snapshot_completed(request_v1.provider_snapshot, lifecycle)
    finally:
        pool.close()


@pytest.mark.unit
def test_same_request_resumes_partially_attested_checkpoint_without_fork(
    tmp_path: Path,
) -> None:
    lifecycle, pool = _store(tmp_path)
    snapshot = _Recorder()
    catalog = _Recorder()
    logs = _Recorder()
    committer = IngestionEvidenceCommitter(
        ports=_ports(lifecycle, snapshot, catalog, logs),
        now=lambda: datetime(2026, 7, 18, 9, 0, tzinfo=UTC),
    )
    request = _request()

    try:
        lifecycle.plan_partition(_planned(request))
        lifecycle.advance_partition(
            request.chunk_id,
            PartitionLifecycleStatus.PAYLOAD_COMMITTED,
            occurred_at=datetime(2026, 7, 18, 8, 41, tzinfo=UTC),
            evidence_id=_payload_evidence_id(request),
        )
        snapshot.values.append(request.provider_snapshot)

        outcome = committer.commit(request)

        assert outcome.completed is True
        assert outcome.chunk_id == request.chunk_id
        assert snapshot_completed(request.provider_snapshot, lifecycle)
        # 幂等重放:每个持久化端口都只见到同一份快照内容。
        assert set(snapshot.values) == {request.provider_snapshot}
    finally:
        pool.close()


@pytest.mark.unit
def test_reingestion_backfills_observation_for_legacy_snapshot_row(
    tmp_path: Path,
) -> None:
    from ditto_data.catalog.source_snapshot_store import SQLiteProviderSnapshotStore

    lifecycle, pool = _store(tmp_path)
    snapshots = SQLiteProviderSnapshotStore(SQLiteClient(pool))
    catalog = _Recorder()
    logs = _Recorder()
    committer = IngestionEvidenceCommitter(
        ports=_ports(lifecycle, snapshots, catalog, logs),
        now=lambda: datetime(2026, 7, 18, 9, 0, tzinfo=UTC),
    )
    request = _request()

    try:
        snapshots.append_snapshot(request.provider_snapshot)
        client = SQLiteClient(pool)
        # 模拟事件账本出现之前的遗留行:事件表没有观察记录。
        client.execute(
            "DELETE FROM provider_snapshot_observation_events WHERE snapshot_id = ?",
            [request.provider_snapshot.snapshot_id],
        )
        client.commit()
        assert snapshots.get_observed_at(request.provider_snapshot.snapshot_id) is None
        lifecycle.plan_partition(_planned(request))
        outcome = committer.commit(request)

        assert outcome.completed is True
        assert (
            snapshots.get_observed_at(request.provider_snapshot.snapshot_id) is not None
        )
    finally:
        pool.close()


@pytest.mark.unit
def test_schema_change_after_unbound_intent_forks_new_revision(tmp_path: Path) -> None:
    lifecycle, pool = _store(tmp_path)
    recorder = _Recorder()
    committer = IngestionEvidenceCommitter(
        ports=_ports(lifecycle, recorder, recorder, recorder),
        now=lambda: datetime(2026, 7, 18, 9, 0, tzinfo=UTC),
    )
    request_v1 = _request()
    request_v2 = _request(schema_version="market.stock_daily.v2")

    try:
        lifecycle.plan_partition(
            _planned(
                request_v1,
                # Legacy intents bind only the value checksum.
                payload_id=f"intent:{request_v1.provider_snapshot.checksum}",
            )
        )

        outcome = committer.commit(request_v2)

        assert outcome.completed is True
        assert outcome.chunk_id != request_v1.chunk_id
        assert outcome.chunk_id.startswith(f"{request_v1.chunk_id}:revision:")
        fork_events = lifecycle.list_events(outcome.chunk_id)
        assert [event.to_status for event in fork_events] == [
            PartitionLifecycleStatus.PLANNED,
            PartitionLifecycleStatus.PAYLOAD_COMMITTED,
            PartitionLifecycleStatus.COMPLETE,
        ]
        base = lifecycle.get_checkpoint(request_v1.chunk_id)
        assert base is not None
        assert base.status is PartitionLifecycleStatus.PLANNED
    finally:
        pool.close()


@pytest.mark.unit
def test_completed_chunk_rejects_same_chunk_different_checksum(
    tmp_path: Path,
) -> None:
    """COMPLETE 后同 chunk 不同 checksum 必须拒绝复用并走独立 revision。"""
    lifecycle, pool = _store(tmp_path)
    recorder = _Recorder()
    committer = IngestionEvidenceCommitter(
        ports=_ports(lifecycle, recorder, recorder, recorder),
        now=lambda: datetime(2026, 7, 18, 9, 0, tzinfo=UTC),
    )
    request = _request()

    try:
        assert committer.commit(request).completed
        different_checksum = _request(checksum="sha256:revised-payload")

        outcome = committer.commit(different_checksum)

        # 不同内容不复用已完成的 chunk 身份,而是独立 revision 完成落证。
        assert outcome.completed is True
        assert outcome.chunk_id != request.chunk_id
        assert outcome.chunk_id.startswith(f"{request.chunk_id}:revision:")
        base = lifecycle.get_checkpoint(request.chunk_id)
        assert base is not None
        assert base.status is PartitionLifecycleStatus.COMPLETE
        assert base.complete_evidence_id == request.provider_snapshot.snapshot_id
        assert not lifecycle.list_incomplete()
    finally:
        pool.close()
