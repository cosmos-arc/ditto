"""Machine builder for independently reviewable R2 certification reports."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from hashlib import sha256
from pathlib import Path

import orjson
from ditto_data.catalog import (
    DataCatalogEntry,
    DataCatalogReader,
    default_dataset_metadata,
)
from ditto_data.catalog.certification import (
    CertificationEvidence,
    DatasetCertificationReport,
    EvidenceCheck,
)
from ditto_data.catalog.coverage import CoverageCollector, CoverageException
from ditto_data.catalog.license import DatasetLicenseReader
from ditto_data.catalog.source_snapshot import ProviderSnapshot, ProviderSnapshotReader
from ditto_data.ingestion.partition_state import (
    PartitionCheckpoint,
    PartitionLifecycleReader,
    PartitionLifecycleStatus,
)

from ditto_application.exceptions import AppProcessError

__all__ = [
    "AddressedCertificationEvidence",
    "CertificationBuildRequest",
    "DataProductCertificationBuilder",
]

_SHA256_HEX_LENGTH = 64


@dataclass(frozen=True, slots=True)
class AddressedCertificationEvidence:
    """One external artifact whose local bytes must match its declared address."""

    name: str
    evidence_uri: str
    local_path: Path
    sha256_hex: str

    def verify(self) -> EvidenceCheck:
        """Hash the artifact and fail closed before it can enter a report."""
        if not self.name or not self.evidence_uri:
            raise AppProcessError("certification evidence name and URI are required")
        if len(self.sha256_hex) != _SHA256_HEX_LENGTH:
            raise AppProcessError("certification evidence SHA-256 is invalid")
        try:
            actual = sha256(self.local_path.read_bytes()).hexdigest()
        except OSError as error:
            raise AppProcessError(
                f"certification evidence is unreadable: {self.local_path}"
            ) from error
        if actual != self.sha256_hex:
            raise AppProcessError(
                f"certification evidence hash mismatch: {self.local_path}"
            )
        return EvidenceCheck(
            name=self.name,
            evidence_uri=self.evidence_uri,
            passed=True,
        )


@dataclass(frozen=True, slots=True)
class CertificationBuildRequest:
    """Explicit product interval and independent operational evidence inputs."""

    dataset_id: str
    profile: str
    target_to: date
    expected_dates: tuple[date, ...]
    generated_at: datetime
    recovery_evidence: AddressedCertificationEvidence
    consumer_evidence: AddressedCertificationEvidence
    target_from: date | None = None
    exceptions: tuple[CoverageException, ...] = ()
    snapshot_ids: tuple[str, ...] = ()


class DataProductCertificationBuilder:
    """Derive frozen machine facts from the durable R2 evidence chain."""

    def __init__(
        self,
        *,
        catalog_reader: DataCatalogReader,
        snapshot_reader: ProviderSnapshotReader,
        license_reader: DatasetLicenseReader,
        lifecycle_reader: PartitionLifecycleReader,
    ) -> None:
        self._catalog_reader = catalog_reader
        self._snapshot_reader = snapshot_reader
        self._license_reader = license_reader
        self._lifecycle_reader = lifecycle_reader

    def build(self, request: CertificationBuildRequest) -> DatasetCertificationReport:
        """Verify coverage and evidence closure, then create an immutable report."""
        metadata = default_dataset_metadata().get(request.dataset_id)
        if metadata is None or metadata.dataset_spec is None:
            raise AppProcessError(
                f"dataset has no product contract: {request.dataset_id}"
            )
        snapshots = self._selected_snapshots(request)
        selected_ids = frozenset(request.snapshot_ids) or None
        coverage = CoverageCollector(
            self._catalog_reader,
            self._snapshot_reader,
        ).collect(
            request.dataset_id,
            target_from=request.target_from,
            target_to=request.target_to,
            expected_dates=request.expected_dates,
            exceptions=request.exceptions,
            snapshot_ids=selected_ids,
        )
        if not coverage.is_complete:
            raise AppProcessError(
                f"dataset coverage is incomplete: {request.dataset_id}"
            )
        entries, checkpoints = self._evidence_chain(request, snapshots)
        self._verify_snapshot_bindings(request, snapshots, entries, checkpoints)

        stage_digest = self._verify_lifecycle_stages(checkpoints)
        latest_request_end = max(
            date.fromisoformat(snapshot.request_end) for snapshot in snapshots
        )
        if latest_request_end < request.target_to:
            raise AppProcessError(
                "provider evidence is stale before certification target"
            )

        schema_versions = tuple(
            sorted({snapshot.schema_version for snapshot in snapshots})
        )
        source_ids = tuple(sorted({snapshot.source for snapshot in snapshots}))
        snapshot_ids = tuple(sorted(snapshot.snapshot_id for snapshot in snapshots))
        license_record_ids = tuple(
            sorted({snapshot.license_record_id for snapshot in snapshots})
        )
        dq_version_digest = sha256(
            orjson.dumps(
                [
                    request.dataset_id,
                    metadata.quality_profile,
                    list(schema_versions),
                ]
            )
        ).hexdigest()
        chain_uri = (
            f"sqlite-evidence://{request.dataset_id}/lifecycle/sha256/{stage_digest}"
        )
        freshness_digest = sha256(
            orjson.dumps([latest_request_end.isoformat(), list(snapshot_ids)])
        ).hexdigest()
        evidence = CertificationEvidence(
            source_ids=source_ids,
            schema_versions=schema_versions,
            snapshot_ids=snapshot_ids,
            dq_rule_version=(f"{metadata.quality_profile}:sha256:{dq_version_digest}"),
            dq_results=(
                EvidenceCheck(
                    name="complete_chunk_dq_stages",
                    evidence_uri=chain_uri,
                    passed=True,
                ),
            ),
            pit_replay_results=(
                EvidenceCheck(
                    name="complete_chunk_pit_universe_replay_stages",
                    evidence_uri=chain_uri,
                    passed=True,
                ),
            ),
            fallback_history=tuple(
                f"source:{source_id}:primary:no-fallback-event"
                for source_id in source_ids
            ),
            override_history=(),
            freshness_results=(
                EvidenceCheck(
                    name="provider_request_through_target",
                    evidence_uri=(
                        f"sqlite-evidence://{request.dataset_id}/freshness/"
                        f"sha256/{freshness_digest}"
                    ),
                    passed=True,
                ),
            ),
            recovery_results=(request.recovery_evidence.verify(),),
            license_record_ids=license_record_ids,
            consumer_results=(request.consumer_evidence.verify(),),
        )
        return DatasetCertificationReport.create(
            dataset_id=request.dataset_id,
            profile=request.profile,
            coverage=coverage,
            evidence=evidence,
            generated_at=request.generated_at,
        )

    def _selected_snapshots(
        self,
        request: CertificationBuildRequest,
    ) -> tuple[ProviderSnapshot, ...]:
        if request.snapshot_ids != tuple(sorted(set(request.snapshot_ids))):
            raise AppProcessError(
                "certification snapshot IDs must be unique and sorted"
            )
        selected_ids = frozenset(request.snapshot_ids) or None
        snapshots = tuple(
            snapshot
            for snapshot in self._snapshot_reader.list_snapshots(
                dataset_id=request.dataset_id
            )
            if selected_ids is None or snapshot.snapshot_id in selected_ids
        )
        if (
            selected_ids is not None
            and frozenset(snapshot.snapshot_id for snapshot in snapshots)
            != selected_ids
        ):
            raise AppProcessError(
                "certification snapshot allowlist contains unknown IDs"
            )
        return snapshots

    def _evidence_chain(
        self,
        request: CertificationBuildRequest,
        snapshots: tuple[ProviderSnapshot, ...],
    ) -> tuple[tuple[DataCatalogEntry, ...], tuple[PartitionCheckpoint, ...]]:
        selected_assets = {snapshot.canonical_asset for snapshot in snapshots}
        entries = tuple(
            entry
            for entry in self._catalog_reader.list_assets()
            if entry.asset.dataset_id == request.dataset_id
            and entry.asset in selected_assets
        )
        selected_intervals = {
            (snapshot.source, snapshot.request_start, snapshot.request_end)
            for snapshot in snapshots
        }

        def selected(checkpoint: PartitionCheckpoint) -> bool:
            return (
                checkpoint.source,
                checkpoint.request_start,
                checkpoint.request_end,
            ) in selected_intervals

        checkpoints = tuple(
            checkpoint
            for checkpoint in self._lifecycle_reader.list_complete(
                dataset_id=request.dataset_id
            )
            if selected(checkpoint)
        )
        incomplete = tuple(
            checkpoint
            for checkpoint in self._lifecycle_reader.list_incomplete(
                dataset_id=request.dataset_id
            )
            if selected(checkpoint)
        )
        if not entries or not snapshots or not checkpoints:
            raise AppProcessError(
                f"dataset evidence chain is empty: {request.dataset_id}"
            )
        if incomplete:
            raise AppProcessError(
                f"dataset has incomplete evidence chunks: {request.dataset_id}"
            )
        return entries, checkpoints

    def _verify_snapshot_bindings(
        self,
        request: CertificationBuildRequest,
        snapshots: tuple[ProviderSnapshot, ...],
        entries: tuple[DataCatalogEntry, ...],
        checkpoints: tuple[PartitionCheckpoint, ...],
    ) -> None:
        assets = {entry.asset: entry for entry in entries}
        checkpoint_intervals = {
            (item.source, item.request_start, item.request_end) for item in checkpoints
        }
        for snapshot in snapshots:
            if snapshot.snapshot_id != snapshot.expected_snapshot_id():
                raise AppProcessError("provider snapshot identity mismatch")
            entry = assets.get(snapshot.canonical_asset)
            if entry is None:
                raise AppProcessError("provider snapshot canonical asset is missing")
            canonical_row_count = entry.schema.row_count
            if canonical_row_count is None:
                raise AppProcessError("provider snapshot catalog row count is missing")
            if canonical_row_count > snapshot.row_count:
                raise AppProcessError(
                    "canonical row count exceeds provider payload row count"
                )
            if entry.schema.schema_version != snapshot.schema_version:
                raise AppProcessError("provider snapshot/catalog schema mismatch")
            license_record = self._license_reader.get_license(
                snapshot.license_record_id
            )
            if (
                license_record is None
                or license_record.dataset_id != request.dataset_id
                or license_record.source != snapshot.source
            ):
                raise AppProcessError("provider snapshot license binding mismatch")
            interval = (snapshot.source, snapshot.request_start, snapshot.request_end)
            if interval not in checkpoint_intervals:
                raise AppProcessError("provider snapshot has no COMPLETE checkpoint")

    def _verify_lifecycle_stages(
        self,
        checkpoints: tuple[PartitionCheckpoint, ...],
    ) -> str:
        payload: list[object] = []
        required = {
            PartitionLifecycleStatus.PIT_PASSED,
            PartitionLifecycleStatus.DQ_PASSED,
            PartitionLifecycleStatus.COMPLETE,
        }
        for checkpoint in checkpoints:
            chunk_id = checkpoint.chunk_id
            events = self._lifecycle_reader.list_events(chunk_id)
            stages = {event.to_status for event in events}
            if not required.issubset(stages):
                raise AppProcessError(
                    f"checkpoint stage evidence is incomplete: {chunk_id}"
                )
            payload.append(
                [
                    chunk_id,
                    checkpoint.request_start,
                    checkpoint.request_end,
                    [event.to_status.value for event in events],
                ]
            )
        return sha256(orjson.dumps(payload)).hexdigest()
