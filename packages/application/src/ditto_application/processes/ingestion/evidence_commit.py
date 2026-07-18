"""Fail-closed durable evidence saga for R2 ingestion partitions."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Protocol

from ditto_data.catalog import (
    DataCatalogEntry,
    DataCatalogWriter,
    DatasetLicenseReader,
    ProviderSnapshot,
    ProviderSnapshotWriter,
)
from ditto_data.ingestion.partition_state import (
    PartitionCheckpoint,
    PartitionLifecycleReader,
    PartitionLifecycleStatus,
    PartitionLifecycleWriter,
)
from ditto_data.lineage import DataLineageRecorder, LineageEvent
from ditto_data.models.ingestion import IngestionLog, IngestionStatus

__all__ = [
    "EvidenceCommitOutcome",
    "EvidenceCommitPorts",
    "EvidenceCommitRequest",
    "IngestionEvidenceCommitter",
]


class _IngestionLogWriter(Protocol):
    def save_log(self, log: IngestionLog) -> IngestionLog:
        """Persist one ingestion log record."""
        ...


@dataclass(frozen=True, slots=True)
class EvidenceCommitRequest:
    """All immutable facts required to attest one persisted payload."""

    chunk_id: str
    dataset_id: str
    source: str
    request_start: str
    request_end: str
    provider_snapshot: ProviderSnapshot
    catalog_entry: DataCatalogEntry
    lineage_event: LineageEvent
    success_log: IngestionLog
    quality_attested: bool = True
    retry_budget: int = 3


@dataclass(frozen=True, slots=True)
class EvidenceCommitOutcome:
    """Fail-closed saga outcome safe to map to an ingestion result."""

    chunk_id: str
    completed: bool
    error_code: str | None = None


@dataclass(frozen=True, slots=True)
class EvidenceCommitPorts:
    """Durable ports participating in one evidence commit saga."""

    lifecycle_reader: PartitionLifecycleReader
    lifecycle_writer: PartitionLifecycleWriter
    snapshot_writer: ProviderSnapshotWriter
    license_reader: DatasetLicenseReader
    catalog_writer: DataCatalogWriter
    lineage_recorder: DataLineageRecorder
    ingestion_log_store: _IngestionLogWriter


class IngestionEvidenceCommitter:
    """Advance one partition only after every evidence write is durable."""

    def __init__(
        self,
        *,
        ports: EvidenceCommitPorts,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._ports = ports
        self._now = now or (lambda: datetime.now(UTC))

    def commit(self, request: EvidenceCommitRequest) -> EvidenceCommitOutcome:
        """Commit or repair the evidence chain without repeating durable stages."""
        self._validate_request(request)
        preparation = self._prepare_payload(request)
        if preparation is not None:
            return preparation

        catalog_failure = self._commit_catalog_evidence(request)
        if catalog_failure is not None:
            return catalog_failure
        lineage_failure = self._commit_lineage_evidence(request)
        if lineage_failure is not None:
            return lineage_failure
        log_failure = self._commit_success_log(request)
        if log_failure is not None:
            return log_failure
        return self._complete(request)

    def _prepare_payload(
        self, request: EvidenceCommitRequest
    ) -> EvidenceCommitOutcome | None:
        try:
            checkpoint = self._prepare_checkpoint(request)
            if checkpoint.status is PartitionLifecycleStatus.COMPLETE:
                return EvidenceCommitOutcome(request.chunk_id, completed=True)
            self._advance_payload_stages(checkpoint, request)
        except Exception:
            return EvidenceCommitOutcome(
                request.chunk_id,
                completed=False,
                error_code="PARTITION_LIFECYCLE_FAILED",
            )
        return None

    def _commit_catalog_evidence(
        self, request: EvidenceCommitRequest
    ) -> EvidenceCommitOutcome | None:
        license_error = self._license_error(request)
        if license_error is not None:
            return self._fail(
                request,
                status=PartitionLifecycleStatus.ORPHAN_PAYLOAD,
                error_code=license_error,
            )
        if not request.quality_attested:
            return self._fail(
                request,
                status=PartitionLifecycleStatus.ORPHAN_PAYLOAD,
                error_code="DQ_EVIDENCE_MISSING",
            )

        checkpoint = self._require_checkpoint(request.chunk_id)
        if checkpoint.status is not PartitionLifecycleStatus.PAYLOAD_COMMITTED:
            return None
        try:
            self._ports.snapshot_writer.append_snapshot(request.provider_snapshot)
        except Exception:
            return self._fail(
                request,
                status=PartitionLifecycleStatus.ORPHAN_PAYLOAD,
                error_code="SNAPSHOT_WRITE_FAILED",
            )
        try:
            self._ports.catalog_writer.upsert_asset(request.catalog_entry)
            self._advance(
                request.chunk_id,
                PartitionLifecycleStatus.CATALOG_ATTESTED,
                evidence_id=_catalog_evidence_id(request.catalog_entry),
            )
        except Exception:
            return self._fail(
                request,
                status=PartitionLifecycleStatus.ORPHAN_PAYLOAD,
                error_code="CATALOG_WRITE_FAILED",
            )
        return None

    def _commit_lineage_evidence(
        self, request: EvidenceCommitRequest
    ) -> EvidenceCommitOutcome | None:
        checkpoint = self._require_checkpoint(request.chunk_id)
        if checkpoint.status is not PartitionLifecycleStatus.CATALOG_ATTESTED:
            return None
        try:
            self._ports.lineage_recorder.record_event(request.lineage_event)
            self._advance(
                request.chunk_id,
                PartitionLifecycleStatus.LINEAGE_RECORDED,
                evidence_id=request.lineage_event.run_id,
            )
        except Exception:
            return self._fail(
                request,
                status=PartitionLifecycleStatus.CATALOG_ONLY,
                error_code="LINEAGE_WRITE_FAILED",
            )
        return None

    def _commit_success_log(
        self, request: EvidenceCommitRequest
    ) -> EvidenceCommitOutcome | None:
        checkpoint = self._require_checkpoint(request.chunk_id)
        if checkpoint.status is not PartitionLifecycleStatus.LINEAGE_RECORDED:
            return None
        try:
            self._ports.ingestion_log_store.save_log(request.success_log)
            self._advance(
                request.chunk_id,
                PartitionLifecycleStatus.SUCCESS_RECORDED,
                evidence_id=_ingestion_log_id(request.success_log),
            )
        except Exception:
            return self._fail(
                request,
                status=PartitionLifecycleStatus.CATALOG_ONLY,
                error_code="SUCCESS_LOG_WRITE_FAILED",
            )
        return None

    def _complete(self, request: EvidenceCommitRequest) -> EvidenceCommitOutcome:
        try:
            self._advance(request.chunk_id, PartitionLifecycleStatus.COMPLETE)
        except Exception:
            return self._fail(
                request,
                status=PartitionLifecycleStatus.LOG_ONLY,
                error_code="PARTITION_COMPLETE_FAILED",
            )
        return EvidenceCommitOutcome(request.chunk_id, completed=True)

    @staticmethod
    def _validate_request(request: EvidenceCommitRequest) -> None:
        if request.provider_snapshot.dataset_id != request.dataset_id:
            raise ValueError("provider snapshot dataset does not match request")
        if request.provider_snapshot.source != request.source:
            raise ValueError("provider snapshot source does not match request")
        if request.catalog_entry.asset != request.provider_snapshot.canonical_asset:
            raise ValueError("catalog and provider snapshot assets do not match")
        if (
            request.success_log.dataset != request.dataset_id
            or request.success_log.source != request.source
            or request.success_log.trade_date != request.request_start
            or request.success_log.status is not IngestionStatus.SUCCESS
            or request.success_log.checksum != request.provider_snapshot.checksum
            or request.success_log.rows != request.provider_snapshot.row_count
        ):
            raise ValueError("success log does not match committed payload evidence")

    def _prepare_checkpoint(
        self, request: EvidenceCommitRequest
    ) -> PartitionCheckpoint:
        checkpoint = self._ports.lifecycle_reader.get_checkpoint(request.chunk_id)
        if checkpoint is None:
            checkpoint = PartitionCheckpoint(
                chunk_id=request.chunk_id,
                dataset_id=request.dataset_id,
                source=request.source,
                request_start=request.request_start,
                request_end=request.request_end,
                status=PartitionLifecycleStatus.PLANNED,
                last_successful_stage=None,
                attempt=1,
                retry_budget=request.retry_budget,
                payload_id=None,
                catalog_asset_id=None,
                lineage_run_id=None,
                ingestion_log_id=None,
                error_code=None,
                updated_at=self._now(),
            )
            self._ports.lifecycle_writer.plan_partition(checkpoint)
            return checkpoint
        if checkpoint.status in {
            PartitionLifecycleStatus.FAILED,
            PartitionLifecycleStatus.QUARANTINED,
            PartitionLifecycleStatus.ORPHAN_PAYLOAD,
            PartitionLifecycleStatus.LOG_ONLY,
            PartitionLifecycleStatus.CATALOG_ONLY,
        }:
            return self._ports.lifecycle_writer.resume_partition(
                request.chunk_id,
                occurred_at=self._now(),
            )
        return checkpoint

    def _advance_payload_stages(
        self,
        checkpoint: PartitionCheckpoint,
        request: EvidenceCommitRequest,
    ) -> PartitionCheckpoint:
        stages = (
            PartitionLifecycleStatus.FETCHED,
            PartitionLifecycleStatus.NORMALIZED,
            PartitionLifecycleStatus.PIT_PASSED,
            PartitionLifecycleStatus.DQ_PASSED,
            PartitionLifecycleStatus.PAYLOAD_COMMITTED,
        )
        current = checkpoint
        stage_index = {
            status: index
            for index, status in enumerate((PartitionLifecycleStatus.PLANNED, *stages))
        }
        if current.status not in stage_index:
            return current
        for stage in stages[stage_index[current.status] :]:
            current = self._ports.lifecycle_writer.advance_partition(
                request.chunk_id,
                stage,
                occurred_at=self._now(),
                evidence_id=(
                    _payload_evidence_id(request)
                    if stage is PartitionLifecycleStatus.PAYLOAD_COMMITTED
                    else None
                ),
            )
        return current

    def _license_error(self, request: EvidenceCommitRequest) -> str | None:
        snapshot = request.provider_snapshot
        record = self._ports.license_reader.get_license(snapshot.license_record_id)
        if (
            record is None
            or record.dataset_id != request.dataset_id
            or record.source != request.source
        ):
            return "LICENSE_EVIDENCE_MISSING"
        request_end = date.fromisoformat(request.request_end)
        if request_end < record.effective_from or (
            record.effective_to is not None and request_end > record.effective_to
        ):
            return "LICENSE_NOT_EFFECTIVE"
        if record.local_cache != "allowed" or record.derivative_compute != "allowed":
            return "LICENSE_PERMISSION_BLOCKED"
        return None

    def _advance(
        self,
        chunk_id: str,
        status: PartitionLifecycleStatus,
        *,
        evidence_id: str | None = None,
    ) -> PartitionCheckpoint:
        return self._ports.lifecycle_writer.advance_partition(
            chunk_id,
            status,
            occurred_at=self._now(),
            evidence_id=evidence_id,
        )

    def _fail(
        self,
        request: EvidenceCommitRequest,
        *,
        status: PartitionLifecycleStatus,
        error_code: str,
    ) -> EvidenceCommitOutcome:
        try:
            self._ports.lifecycle_writer.fail_partition(
                request.chunk_id,
                status,
                error_code=error_code,
                occurred_at=self._now(),
            )
        except Exception:
            return EvidenceCommitOutcome(
                request.chunk_id,
                completed=False,
                error_code="PARTITION_FAILURE_RECORD_FAILED",
            )
        return EvidenceCommitOutcome(
            request.chunk_id,
            completed=False,
            error_code=error_code,
        )

    def _require_checkpoint(self, chunk_id: str) -> PartitionCheckpoint:
        checkpoint = self._ports.lifecycle_reader.get_checkpoint(chunk_id)
        if checkpoint is None:
            raise ValueError(f"missing partition checkpoint: {chunk_id}")
        return checkpoint


def _payload_evidence_id(request: EvidenceCommitRequest) -> str:
    return (
        f"payload:{request.provider_snapshot.checksum}:"
        f"{request.catalog_entry.storage_uri}"
    )


def _catalog_evidence_id(entry: DataCatalogEntry) -> str:
    partitions = ",".join(entry.asset.partition_keys)
    return f"catalog:{entry.asset.namespace}:{entry.asset.dataset_id}:{partitions}"


def _ingestion_log_id(log: IngestionLog) -> str:
    return f"log:{log.source}:{log.dataset}:{log.trade_date}:{log.checksum}"
