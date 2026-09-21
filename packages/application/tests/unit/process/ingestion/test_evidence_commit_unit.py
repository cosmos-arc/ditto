"""Fail-closed ingestion evidence saga tests."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from ditto_application.processes.ingestion.evidence_commit import (
    EvidenceCommitPorts,
    EvidenceCommitRequest,
    IngestionEvidenceCommitter,
    _catalog_evidence_id,
    _ingestion_log_id,
    _payload_evidence_id,
)
from ditto_data.catalog import (
    DataAssetRef,
    DataCatalogEntry,
    DataSchemaFingerprint,
)
from ditto_data.catalog.license import DatasetLicenseDraft, DatasetLicenseRecord
from ditto_data.catalog.snapshot_completion import snapshot_completed
from ditto_data.catalog.source_snapshot import ProviderSnapshot, ProviderSnapshotDraft
from ditto_data.ingestion.partition_state import (
    PartitionCheckpoint,
    PartitionLifecycleStatus,
)
from ditto_data.ingestion.partition_state_store import SQLitePartitionLifecycleStore
from ditto_data.lineage import LineageEvent, LineageInputRef, LineageOutputRef
from ditto_data.models.ingestion import IngestionLog, IngestionStatus
from ditto_platform.foundation import SQLiteClient, SQLitePool


class _LicenseReader:
    def __init__(self, record: DatasetLicenseRecord) -> None:
        self.record = record

    def get_license(self, record_id: str) -> DatasetLicenseRecord | None:
        return self.record if record_id == self.record.record_id else None

    def list_licenses(
        self, *, dataset_id: str | None = None, source: str | None = None
    ) -> tuple[DatasetLicenseRecord, ...]:
        records = (self.record,)
        return tuple(
            record
            for record in records
            if (dataset_id is None or record.dataset_id == dataset_id)
            and (source is None or record.source == source)
        )


class _Recorder:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.values: list[object] = []

    def append_snapshot(self, value: object) -> None:
        self._record(value)

    def upsert_asset(self, value: object) -> None:
        self._record(value)

    def record_event(self, value: object) -> None:
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

    def list_events_for_run(self, run_id: str) -> tuple[LineageEvent, ...]:
        return tuple(
            v for v in self.values if isinstance(v, LineageEvent) and v.run_id == run_id
        )

    def list_events_for_asset(self, asset: DataAssetRef) -> tuple[LineageEvent, ...]:
        return tuple(v for v in self.values if isinstance(v, LineageEvent))

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


def _license() -> DatasetLicenseRecord:
    return DatasetLicenseRecord.create(
        DatasetLicenseDraft(
            dataset_id="stock_daily",
            source="tushare",
            terms_version="fixture-v1",
            effective_from=date(2020, 1, 1),
            effective_to=None,
            local_cache="allowed",
            derivative_compute="allowed",
            display="restricted",
            redistribution="prohibited",
            notes="Test fixture review only.",
            reviewed_by="test-reviewer",
            reviewed_at=datetime(2026, 7, 18, 8, 0, tzinfo=UTC),
        )
    )


def _request(
    license_record: DatasetLicenseRecord,
    schema_version: str = "market.stock_daily.v1",
) -> EvidenceCommitRequest:
    now = datetime(2026, 7, 18, 8, 30, tzinfo=UTC)
    canonical_asset = DataAssetRef(
        dataset_id="stock_daily",
        namespace="market",
        partition_keys=("trade_date=2026-07-17",),
    )
    snapshot = ProviderSnapshot.create(
        ProviderSnapshotDraft(
            dataset_id="stock_daily",
            source="tushare",
            request_start="2026-07-17",
            request_end="2026-07-17",
            schema_version=schema_version,
            checksum="sha256:payload",
            canonical_asset=canonical_asset,
            request_parameters_hash="sha256:request",
            response_metadata=(("snapshot_layer", "normalized_provider_payload"),),
            license_record_id=license_record.record_id,
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
        source_snapshot_id=(
            "snapshot:tushare:stock_daily:2026-07-17:sha256:canonical:quality=l1-l2"
        ),
    )
    lineage = LineageEvent(
        run_id="ingest:tushare:stock_daily:2026-07-17:sha256:canonical",
        operation="ingest",
        inputs=(
            LineageInputRef(
                DataAssetRef(
                    dataset_id="stock_daily",
                    namespace="source",
                    partition_keys=(
                        "source=tushare",
                        "trade_date=2026-07-17",
                    ),
                ),
                role="source",
            ),
        ),
        outputs=(LineageOutputRef(canonical_asset, role="dataset"),),
        timestamp=now,
    )
    return EvidenceCommitRequest(
        chunk_id="chunk:tushare:stock_daily:2026-07-17",
        dataset_id="stock_daily",
        source="tushare",
        request_start="2026-07-17",
        request_end="2026-07-17",
        provider_snapshot=snapshot,
        catalog_entry=catalog_entry,
        lineage_event=lineage,
        success_log=IngestionLog(
            dataset="stock_daily",
            source="tushare",
            trade_date="2026-07-17",
            status=IngestionStatus.SUCCESS,
            checksum="sha256:canonical",
            rows=1,
        ),
    )


def _store(tmp_path: Path) -> tuple[SQLitePartitionLifecycleStore, SQLitePool]:
    pool = SQLitePool(str(tmp_path / "runtime.sqlite"))
    return SQLitePartitionLifecycleStore(SQLiteClient(pool)), pool


@pytest.mark.unit
def test_evidence_commit_reaches_complete_only_after_all_durable_writes(
    tmp_path: Path,
) -> None:
    lifecycle, pool = _store(tmp_path)
    license_record = _license()
    snapshot, catalog, lineage, logs = (_Recorder() for _ in range(4))
    committer = IngestionEvidenceCommitter(
        ports=EvidenceCommitPorts(
            lifecycle_reader=lifecycle,
            lifecycle_writer=lifecycle,
            snapshot_writer=snapshot,
            snapshot_reader=snapshot,
            license_reader=_LicenseReader(license_record),
            catalog_writer=catalog,
            lineage_recorder=lineage,
            lineage_reader=lineage,
            ingestion_log_store=logs,
        ),
        now=lambda: datetime(2026, 7, 18, 9, 0, tzinfo=UTC),
    )

    try:
        outcome = committer.commit(_request(license_record))

        assert outcome.completed is True
        assert outcome.error_code is None
        checkpoint = lifecycle.get_checkpoint(outcome.chunk_id)
        assert checkpoint is not None
        assert checkpoint.status is PartitionLifecycleStatus.COMPLETE
        assert len(snapshot.values) == 1
        assert len(catalog.values) == 1
        assert len(lineage.values) == 1
        assert len(logs.values) == 1
    finally:
        pool.close()


@pytest.mark.unit
def test_license_effective_on_fetch_date_allows_older_observation_date(
    tmp_path: Path,
) -> None:
    lifecycle, pool = _store(tmp_path)
    license_record = replace(_license(), effective_from=date(2026, 7, 18))
    recorder = _Recorder()
    committer = IngestionEvidenceCommitter(
        ports=EvidenceCommitPorts(
            lifecycle_reader=lifecycle,
            lifecycle_writer=lifecycle,
            snapshot_writer=recorder,
            snapshot_reader=recorder,
            license_reader=_LicenseReader(license_record),
            catalog_writer=recorder,
            lineage_recorder=recorder,
            lineage_reader=recorder,
            ingestion_log_store=recorder,
        )
    )

    try:
        outcome = committer.commit(_request(license_record))

        assert outcome.completed is True
        assert outcome.error_code is None
    finally:
        pool.close()


@pytest.mark.unit
def test_license_expired_before_fetch_date_fails_closed(tmp_path: Path) -> None:
    lifecycle, pool = _store(tmp_path)
    license_record = replace(_license(), effective_to=date(2026, 7, 17))
    recorder = _Recorder()
    committer = IngestionEvidenceCommitter(
        ports=EvidenceCommitPorts(
            lifecycle_reader=lifecycle,
            lifecycle_writer=lifecycle,
            snapshot_writer=recorder,
            snapshot_reader=recorder,
            license_reader=_LicenseReader(license_record),
            catalog_writer=recorder,
            lineage_recorder=recorder,
            lineage_reader=recorder,
            ingestion_log_store=recorder,
        )
    )

    try:
        outcome = committer.commit(_request(license_record))

        assert outcome.completed is False
        assert outcome.error_code == "LICENSE_NOT_EFFECTIVE"
    finally:
        pool.close()


@pytest.mark.unit
@pytest.mark.parametrize(
    ("failing_port", "expected_status", "expected_error"),
    [
        ("snapshot", PartitionLifecycleStatus.ORPHAN_PAYLOAD, "SNAPSHOT_WRITE_FAILED"),
        ("catalog", PartitionLifecycleStatus.ORPHAN_PAYLOAD, "CATALOG_WRITE_FAILED"),
        ("lineage", PartitionLifecycleStatus.CATALOG_ONLY, "LINEAGE_WRITE_FAILED"),
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
    license_record = _license()
    ports = {
        name: _Recorder(fail=name == failing_port)
        for name in ("snapshot", "catalog", "lineage", "logs")
    }
    committer = IngestionEvidenceCommitter(
        ports=EvidenceCommitPorts(
            lifecycle_reader=lifecycle,
            lifecycle_writer=lifecycle,
            snapshot_writer=ports["snapshot"],
            snapshot_reader=ports["snapshot"],
            license_reader=_LicenseReader(license_record),
            catalog_writer=ports["catalog"],
            lineage_recorder=ports["lineage"],
            lineage_reader=ports["lineage"],
            ingestion_log_store=ports["logs"],
        ),
        now=lambda: datetime(2026, 7, 18, 9, 0, tzinfo=UTC),
    )

    try:
        outcome = committer.commit(_request(license_record))

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
    license_record = _license()
    snapshot = _Recorder()
    catalog = _Recorder()
    lineage = _Recorder()
    logs = _Recorder()
    committer = IngestionEvidenceCommitter(
        ports=EvidenceCommitPorts(
            lifecycle_reader=lifecycle,
            lifecycle_writer=lifecycle,
            snapshot_writer=snapshot,
            snapshot_reader=snapshot,
            license_reader=_LicenseReader(license_record),
            catalog_writer=catalog,
            lineage_recorder=lineage,
            lineage_reader=lineage,
            ingestion_log_store=logs,
        ),
        now=lambda: datetime(2026, 7, 18, 9, 0, tzinfo=UTC),
    )
    request = _request(license_record)

    try:
        lifecycle.plan_partition(
            PartitionCheckpoint(
                chunk_id=request.chunk_id,
                dataset_id=request.dataset_id,
                source=request.source,
                request_start=request.request_start,
                request_end=request.request_end,
                status=PartitionLifecycleStatus.PLANNED,
                last_successful_stage=None,
                attempt=1,
                retry_budget=3,
                payload_id=None,
                catalog_asset_id=None,
                lineage_run_id=None,
                ingestion_log_id=None,
                error_code=None,
                updated_at=datetime(2026, 7, 18, 8, 40, tzinfo=UTC),
            )
        )
        for status, evidence_id in (
            (PartitionLifecycleStatus.FETCHED, None),
            (PartitionLifecycleStatus.NORMALIZED, None),
            (PartitionLifecycleStatus.PIT_PASSED, None),
            (PartitionLifecycleStatus.DQ_PASSED, None),
            (PartitionLifecycleStatus.PAYLOAD_COMMITTED, _payload_evidence_id(request)),
            (
                PartitionLifecycleStatus.CATALOG_ATTESTED,
                _catalog_evidence_id(
                    request.catalog_entry, request.provider_snapshot.snapshot_id
                ),
            ),
            (PartitionLifecycleStatus.LINEAGE_RECORDED, request.lineage_event.run_id),
            (
                PartitionLifecycleStatus.SUCCESS_RECORDED,
                _ingestion_log_id(request.success_log),
            ),
            # Legacy completions predate snapshot-bound COMPLETE evidence.
            (PartitionLifecycleStatus.COMPLETE, None),
        ):
            lifecycle.advance_partition(
                request.chunk_id,
                status,
                occurred_at=datetime(2026, 7, 18, 8, 41, tzinfo=UTC),
                evidence_id=evidence_id,
            )
        snapshot.values.append(request.provider_snapshot)
        lineage.values.append(request.lineage_event)
        logs.values.append(request.success_log)

        outcome = committer.commit(request)

        assert outcome.completed is True
        assert outcome.error_code is None
        assert outcome.chunk_id.startswith(f"{request.chunk_id}:revision:")
        base_checkpoint = lifecycle.get_checkpoint(request.chunk_id)
        assert base_checkpoint is not None
        assert base_checkpoint.status is PartitionLifecycleStatus.COMPLETE
        base_complete_events = [
            event
            for event in lifecycle.list_events(request.chunk_id)
            if event.to_status is PartitionLifecycleStatus.COMPLETE
        ]
        assert base_complete_events[-1].evidence_id is None
        assert snapshot_completed(request.provider_snapshot, lifecycle)
        assert len(lineage.values) == 1
        assert len(logs.values) == 1

        replay = committer.commit(request)

        assert replay.completed is True
        assert replay.chunk_id == outcome.chunk_id
        assert len(lineage.values) == 1
        assert len(logs.values) == 1
    finally:
        pool.close()


@pytest.mark.unit
def test_schema_version_change_with_same_checksum_reattests_new_snapshot(
    tmp_path: Path,
) -> None:
    lifecycle, pool = _store(tmp_path)
    license_record = _license()
    recorder = _Recorder()
    committer = IngestionEvidenceCommitter(
        ports=EvidenceCommitPorts(
            lifecycle_reader=lifecycle,
            lifecycle_writer=lifecycle,
            snapshot_writer=recorder,
            snapshot_reader=recorder,
            license_reader=_LicenseReader(license_record),
            catalog_writer=recorder,
            lineage_recorder=recorder,
            lineage_reader=recorder,
            ingestion_log_store=recorder,
        ),
        now=lambda: datetime(2026, 7, 18, 9, 0, tzinfo=UTC),
    )
    request_v1 = _request(license_record)
    request_v2 = _request(license_record, schema_version="market.stock_daily.v2")

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
    license_record = _license()
    snapshot = _Recorder()
    catalog = _Recorder(fail=True)
    lineage = _Recorder()
    logs = _Recorder()
    committer = IngestionEvidenceCommitter(
        ports=EvidenceCommitPorts(
            lifecycle_reader=lifecycle,
            lifecycle_writer=lifecycle,
            snapshot_writer=snapshot,
            snapshot_reader=snapshot,
            license_reader=_LicenseReader(license_record),
            catalog_writer=catalog,
            lineage_recorder=lineage,
            lineage_reader=lineage,
            ingestion_log_store=logs,
        ),
        now=lambda: datetime(2026, 7, 18, 9, 0, tzinfo=UTC),
    )
    request = _request(license_record)

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
        assert len(lineage.values) == 1
        assert len(logs.values) == 1
    finally:
        pool.close()


@pytest.mark.unit
def test_schema_change_after_partial_attestation_forks_new_revision(
    tmp_path: Path,
) -> None:
    lifecycle, pool = _store(tmp_path)
    license_record = _license()
    snapshot = _Recorder()
    catalog = _Recorder()
    lineage = _Recorder()
    logs = _Recorder()
    committer = IngestionEvidenceCommitter(
        ports=EvidenceCommitPorts(
            lifecycle_reader=lifecycle,
            lifecycle_writer=lifecycle,
            snapshot_writer=snapshot,
            snapshot_reader=snapshot,
            license_reader=_LicenseReader(license_record),
            catalog_writer=catalog,
            lineage_recorder=lineage,
            lineage_reader=lineage,
            ingestion_log_store=logs,
        ),
        now=lambda: datetime(2026, 7, 18, 9, 0, tzinfo=UTC),
    )
    request_v1 = _request(license_record)
    request_v2 = _request(license_record, schema_version="market.stock_daily.v2")

    try:
        lifecycle.plan_partition(
            PartitionCheckpoint(
                chunk_id=request_v1.chunk_id,
                dataset_id=request_v1.dataset_id,
                source=request_v1.source,
                request_start=request_v1.request_start,
                request_end=request_v1.request_end,
                status=PartitionLifecycleStatus.PLANNED,
                last_successful_stage=None,
                attempt=1,
                retry_budget=3,
                payload_id=None,
                catalog_asset_id=None,
                lineage_run_id=None,
                ingestion_log_id=None,
                error_code=None,
                updated_at=datetime(2026, 7, 18, 8, 40, tzinfo=UTC),
            )
        )
        for status, evidence_id in (
            (PartitionLifecycleStatus.FETCHED, None),
            (PartitionLifecycleStatus.NORMALIZED, None),
            (PartitionLifecycleStatus.PIT_PASSED, None),
            (PartitionLifecycleStatus.DQ_PASSED, None),
            (
                PartitionLifecycleStatus.PAYLOAD_COMMITTED,
                _payload_evidence_id(request_v1),
            ),
            (
                PartitionLifecycleStatus.CATALOG_ATTESTED,
                _catalog_evidence_id(
                    request_v1.catalog_entry,
                    request_v1.provider_snapshot.snapshot_id,
                ),
            ),
        ):
            lifecycle.advance_partition(
                request_v1.chunk_id,
                status,
                occurred_at=datetime(2026, 7, 18, 8, 41, tzinfo=UTC),
                evidence_id=evidence_id,
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
    license_record = _license()
    snapshot = _Recorder()
    catalog = _Recorder()
    lineage = _Recorder()
    logs = _Recorder()
    committer = IngestionEvidenceCommitter(
        ports=EvidenceCommitPorts(
            lifecycle_reader=lifecycle,
            lifecycle_writer=lifecycle,
            snapshot_writer=snapshot,
            snapshot_reader=snapshot,
            license_reader=_LicenseReader(license_record),
            catalog_writer=catalog,
            lineage_recorder=lineage,
            lineage_reader=lineage,
            ingestion_log_store=logs,
        ),
        now=lambda: datetime(2026, 7, 18, 9, 0, tzinfo=UTC),
    )
    request = _request(license_record)

    try:
        lifecycle.plan_partition(
            PartitionCheckpoint(
                chunk_id=request.chunk_id,
                dataset_id=request.dataset_id,
                source=request.source,
                request_start=request.request_start,
                request_end=request.request_end,
                status=PartitionLifecycleStatus.PLANNED,
                last_successful_stage=None,
                attempt=1,
                retry_budget=3,
                payload_id=None,
                catalog_asset_id=None,
                lineage_run_id=None,
                ingestion_log_id=None,
                error_code=None,
                updated_at=datetime(2026, 7, 18, 8, 40, tzinfo=UTC),
            )
        )
        for status, evidence_id in (
            (PartitionLifecycleStatus.FETCHED, None),
            (PartitionLifecycleStatus.NORMALIZED, None),
            (PartitionLifecycleStatus.PIT_PASSED, None),
            (PartitionLifecycleStatus.DQ_PASSED, None),
            (PartitionLifecycleStatus.PAYLOAD_COMMITTED, _payload_evidence_id(request)),
            (
                PartitionLifecycleStatus.CATALOG_ATTESTED,
                _catalog_evidence_id(
                    request.catalog_entry, request.provider_snapshot.snapshot_id
                ),
            ),
        ):
            lifecycle.advance_partition(
                request.chunk_id,
                status,
                occurred_at=datetime(2026, 7, 18, 8, 41, tzinfo=UTC),
                evidence_id=evidence_id,
            )
        snapshot.values.append(request.provider_snapshot)

        outcome = committer.commit(request)

        assert outcome.completed is True
        assert outcome.chunk_id == request.chunk_id
        assert snapshot_completed(request.provider_snapshot, lifecycle)
        assert len(snapshot.values) == 1
    finally:
        pool.close()
