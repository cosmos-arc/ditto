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
)
from ditto_data.catalog import (
    DataAssetRef,
    DataCatalogEntry,
    DataSchemaFingerprint,
)
from ditto_data.catalog.license import DatasetLicenseDraft, DatasetLicenseRecord
from ditto_data.catalog.source_snapshot import ProviderSnapshot, ProviderSnapshotDraft
from ditto_data.ingestion.partition_state import PartitionLifecycleStatus
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


def _request(license_record: DatasetLicenseRecord) -> EvidenceCommitRequest:
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
            schema_version="market.stock_daily.v1",
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
            license_reader=_LicenseReader(license_record),
            catalog_writer=catalog,
            lineage_recorder=lineage,
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
            license_reader=_LicenseReader(license_record),
            catalog_writer=recorder,
            lineage_recorder=recorder,
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
            license_reader=_LicenseReader(license_record),
            catalog_writer=recorder,
            lineage_recorder=recorder,
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
            license_reader=_LicenseReader(license_record),
            catalog_writer=ports["catalog"],
            lineage_recorder=ports["lineage"],
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
            license_reader=_LicenseReader(license_record),
            catalog_writer=catalog,
            lineage_recorder=lineage,
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
