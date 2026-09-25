"""Fail-closed durable evidence saga for R2 ingestion partitions."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from hashlib import sha256
from typing import Protocol

from ditto_data.catalog import (
    DataCatalogEntry,
    DataCatalogWriter,
)
from ditto_data.catalog.license import DatasetLicenseReader
from ditto_data.catalog.provider_payload import ProviderPayloadArtifact
from ditto_data.catalog.source_snapshot import (
    ProviderSnapshot,
    ProviderSnapshotReader,
    ProviderSnapshotWriter,
)
from ditto_data.ingestion.partition_state import (
    PartitionCheckpoint,
    PartitionLifecycleReader,
    PartitionLifecycleStatus,
    PartitionLifecycleWriter,
)
from ditto_data.lineage import DataLineageReader, DataLineageRecorder, LineageEvent
from ditto_data.models.ingestion import IngestionLog, IngestionStatus

from ditto_application.exceptions import AppProcessError

__all__ = [
    "EvidenceCommitOutcome",
    "EvidenceCommitPorts",
    "EvidenceCommitRequest",
    "IngestionEvidenceCommitter",
    "PartitionWriteIntent",
]


class _IngestionLogWriter(Protocol):
    def get_log(
        self, dataset: str, source: str, trade_date: str
    ) -> IngestionLog | None:
        """Read the durable result before retrying its write."""
        ...

    def save_log(self, log: IngestionLog) -> IngestionLog:
        """Persist one ingestion log record."""
        ...


@dataclass(frozen=True, slots=True)
class PartitionWriteIntent:
    """A retained input to apply, not proof of a committed canonical write."""

    chunk_id: str
    request_start: str
    request_end: str
    payload: ProviderPayloadArtifact
    snapshot_id: str | None = None


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
    # 摄取/处理日，默认等于覆盖起点。success log 的 trade_date 必须等于它，
    # 而不是等于 provider 覆盖区间的起点（日历日更的覆盖起点是年初）。
    ingestion_date: str | None = None


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
    snapshot_reader: ProviderSnapshotReader
    license_reader: DatasetLicenseReader
    catalog_writer: DataCatalogWriter
    lineage_recorder: DataLineageRecorder
    lineage_reader: DataLineageReader
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

    def prepare_payload_write(self, intent: PartitionWriteIntent) -> None:
        """Persist a resumable intent before any canonical file can be changed."""
        chunk_id = self._revision_id(
            intent.chunk_id,
            intent.payload.checksum,
            snapshot_id=intent.snapshot_id,
        )
        if self._ports.lifecycle_reader.get_checkpoint(chunk_id) is not None:
            return
        self._ports.lifecycle_writer.plan_partition(
            PartitionCheckpoint(
                chunk_id=chunk_id,
                dataset_id=intent.payload.dataset_id,
                source=intent.payload.source,
                request_start=intent.request_start,
                request_end=intent.request_end,
                status=PartitionLifecycleStatus.PLANNED,
                last_successful_stage=None,
                attempt=1,
                retry_budget=3,
                payload_id=(
                    f"intent:{intent.payload.checksum}:{intent.snapshot_id}"
                    if intent.snapshot_id is not None
                    else f"intent:{intent.payload.checksum}"
                ),
                catalog_asset_id=None,
                lineage_run_id=None,
                ingestion_log_id=None,
                error_code=None,
                updated_at=self._now(),
            )
        )

    def commit(self, request: EvidenceCommitRequest) -> EvidenceCommitOutcome:
        """Commit or repair the evidence chain without repeating durable stages."""
        self._validate_request(request)
        request = self._versioned_request(request)
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

    def _versioned_request(
        self, request: EvidenceCommitRequest
    ) -> EvidenceCommitRequest:
        return replace(
            request,
            chunk_id=self._revision_id(
                request.chunk_id,
                request.provider_snapshot.checksum,
                snapshot_id=request.provider_snapshot.snapshot_id,
                payload_evidence_id=_payload_evidence_id(request),
            ),
        )

    def _revision_id(
        self,
        chunk_id: str,
        checksum: str,
        *,
        snapshot_id: str | None = None,
        payload_evidence_id: str | None = None,
    ) -> str:
        checkpoint = self._ports.lifecycle_reader.get_latest_checkpoint(chunk_id)
        if checkpoint is None:
            return chunk_id
        payload_id = checkpoint.payload_id
        if (
            payload_id is None
            or (payload_id == f"intent:{checksum}" and snapshot_id is None)
            or (
                snapshot_id is not None
                and payload_id == f"intent:{checksum}:{snapshot_id}"
            )
            or (
                payload_id.startswith(f"payload:{checksum}:")
                and not self._identity_conflict(
                    checkpoint, snapshot_id, payload_evidence_id
                )
            )
        ):
            return checkpoint.chunk_id
        revision = sha256(repr((checkpoint.chunk_id, checksum)).encode()).hexdigest()
        return f"{chunk_id}:revision:{revision}"

    def _identity_conflict(
        self,
        checkpoint: PartitionCheckpoint,
        snapshot_id: str | None,
        payload_evidence_id: str | None,
    ) -> bool:
        """Reuse must prove the recorded evidence belongs to this snapshot."""
        if checkpoint.status is PartitionLifecycleStatus.COMPLETE:
            attested = next(
                (
                    event.evidence_id
                    for event in self._ports.lifecycle_reader.list_events(
                        checkpoint.chunk_id
                    )
                    if event.to_status is PartitionLifecycleStatus.COMPLETE
                    and event.evidence_id is not None
                ),
                None,
            )
            if attested is None:
                return True
            return snapshot_id is not None and attested != snapshot_id
        return (
            checkpoint.payload_id is not None
            and payload_evidence_id is not None
            and checkpoint.payload_id != payload_evidence_id
        )

    def _prepare_payload(
        self, request: EvidenceCommitRequest
    ) -> EvidenceCommitOutcome | None:
        try:
            checkpoint = self._prepare_checkpoint(request)
            if checkpoint.status is PartitionLifecycleStatus.COMPLETE:
                self._ports.snapshot_writer.append_snapshot(request.provider_snapshot)
                self._persist_success_log(request.success_log)
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
            # The idempotent append also backfills the observation ledger for
            # upgraded stores whose legacy snapshot rows predate observations.
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
            event = request.lineage_event
            existing = self._ports.lineage_reader.list_events_for_run(event.run_id)
            if not existing:
                self._ports.lineage_recorder.record_event(event)
            elif (
                len(existing) != 1
                or replace(event, timestamp=existing[0].timestamp) != existing[0]
            ):
                raise AppProcessError("immutable ingestion lineage conflict")
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
            self._persist_success_log(request.success_log)
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

    def _persist_success_log(self, log: IngestionLog) -> None:
        existing = self._ports.ingestion_log_store.get_log(
            log.dataset, log.source, log.trade_date
        )
        if existing is None or (existing.status, existing.checksum, existing.rows) != (
            log.status,
            log.checksum,
            log.rows,
        ):
            self._ports.ingestion_log_store.save_log(log)

    def _complete(self, request: EvidenceCommitRequest) -> EvidenceCommitOutcome:
        try:
            self._advance(
                request.chunk_id,
                PartitionLifecycleStatus.COMPLETE,
                evidence_id=request.provider_snapshot.snapshot_id,
            )
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
            raise AppProcessError("provider snapshot dataset does not match request")
        if request.provider_snapshot.source != request.source:
            raise AppProcessError("provider snapshot source does not match request")
        if request.catalog_entry.asset != request.provider_snapshot.canonical_asset:
            raise AppProcessError("catalog and provider snapshot assets do not match")
        if (
            request.success_log.dataset != request.dataset_id
            or request.success_log.source != request.source
            or request.success_log.trade_date
            != (request.ingestion_date or request.request_start)
            or request.success_log.status is not IngestionStatus.SUCCESS
            or not isinstance(request.success_log.checksum, str)
            or not request.success_log.checksum
            or request.success_log.rows != request.catalog_entry.schema.row_count
            or not isinstance(request.catalog_entry.source_snapshot_id, str)
            or f":{request.success_log.checksum}"
            not in request.catalog_entry.source_snapshot_id
            or f":{request.success_log.checksum}" not in request.lineage_event.run_id
        ):
            raise AppProcessError(
                "success log does not match committed canonical evidence"
            )

    def _prepare_checkpoint(
        self, request: EvidenceCommitRequest
    ) -> PartitionCheckpoint:
        checkpoint = self._ports.lifecycle_reader.get_checkpoint(request.chunk_id)
        if checkpoint is not None and (
            (
                checkpoint.dataset_id,
                checkpoint.source,
                checkpoint.request_start,
                checkpoint.request_end,
            )
            != (
                request.dataset_id,
                request.source,
                request.request_start,
                request.request_end,
            )
            or checkpoint.payload_id
            not in {
                None,
                f"intent:{request.provider_snapshot.checksum}",
                _intent_evidence_id(request),
                _payload_evidence_id(request),
            }
            or checkpoint.lineage_run_id not in {None, request.lineage_event.run_id}
        ):
            raise AppProcessError("partition checkpoint identity conflict")
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
        access_date = snapshot.created_at.date()
        if access_date < record.effective_from or (
            record.effective_to is not None and access_date > record.effective_to
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
            raise AppProcessError(f"missing partition checkpoint: {chunk_id}")
        return checkpoint


def _intent_evidence_id(request: EvidenceCommitRequest) -> str:
    return (
        f"intent:{request.provider_snapshot.checksum}:"
        f"{request.provider_snapshot.snapshot_id}"
    )


def _payload_evidence_id(request: EvidenceCommitRequest) -> str:
    """Bind the committed payload stage to one exact provider snapshot."""
    return (
        f"payload:{request.provider_snapshot.checksum}:"
        f"{request.catalog_entry.storage_uri}:{request.provider_snapshot.snapshot_id}"
    )


def _catalog_evidence_id(entry: DataCatalogEntry) -> str:
    partitions = ",".join(entry.asset.partition_keys)
    return f"catalog:{entry.asset.namespace}:{entry.asset.dataset_id}:{partitions}"


def _ingestion_log_id(log: IngestionLog) -> str:
    return f"log:{log.source}:{log.dataset}:{log.trade_date}:{log.checksum}"
