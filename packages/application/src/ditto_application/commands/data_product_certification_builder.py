"""Machine builder for independently reviewable R2 certification reports."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any, cast

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
from ditto_data.catalog.field_evidence import (
    CertifiedField,
    consumer_input_digest,
    field_from_payload,
)
from ditto_data.catalog.license import DatasetLicenseReader
from ditto_data.catalog.snapshot_completion import (
    checkpoint_matches_snapshot,
    snapshot_completed,
)
from ditto_data.catalog.source_snapshot import ProviderSnapshot, ProviderSnapshotReader
from ditto_data.ingestion.partition_state import (
    PartitionCheckpoint,
    PartitionLifecycleReader,
    PartitionLifecycleStatus,
)
from ditto_data.services.metadata.calendar import CalendarService

from ditto_application.exceptions import AppProcessError

__all__ = [
    "AddressedCertificationEvidence",
    "CertificationBuildRequest",
    "DataProductCertificationBuilder",
    "load_certified_field_claims",
]

_SHA256_HEX_LENGTH = 64


def load_certified_field_claims(path: Path) -> tuple[CertifiedField, ...]:
    """Load reviewed field claims exactly as certification reports serialize them."""
    try:
        decoded = orjson.loads(path.read_bytes())
    except (OSError, ValueError) as exc:
        raise AppProcessError(f"certified field claims are unreadable: {exc}") from exc
    if type(decoded) is not list or not all(
        type(item) is dict for item in cast(list[object], decoded)
    ):
        raise AppProcessError("certified field claims must be an array of objects")
    try:
        claims = tuple(
            field_from_payload(item) for item in cast(list[dict[str, Any]], decoded)
        )
    except (AttributeError, TypeError, ValueError, KeyError) as exc:
        raise AppProcessError(f"certified field claim is invalid: {exc}") from exc
    if not claims:
        raise AppProcessError("certified field claims must not be empty")
    return claims


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
    certified_fields: tuple[CertifiedField, ...] = ()


class DataProductCertificationBuilder:
    """Derive frozen machine facts from the durable R2 evidence chain."""

    def __init__(
        self,
        *,
        catalog_reader: DataCatalogReader,
        snapshot_reader: ProviderSnapshotReader,
        license_reader: DatasetLicenseReader,
        lifecycle_reader: PartitionLifecycleReader,
        calendar: CalendarService | None = None,
    ) -> None:
        self._catalog_reader = catalog_reader
        self._snapshot_reader = snapshot_reader
        self._license_reader = license_reader
        self._lifecycle_reader = lifecycle_reader
        self._calendar = calendar

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
        self._verify_snapshot_bindings(request, snapshots, entries)
        _verify_consumer_bindings(request)
        self._verify_certified_fields(request, snapshots, entries)

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
            certified_fields=tuple(
                self._resolve_field_time(field) for field in request.certified_fields
            ),
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

    def _resolve_field_time(self, field: CertifiedField) -> CertifiedField:
        if field.time_precision != "date":
            return field
        if (
            self._calendar is None
            or field.publication_at is None
            or field.available_at is None
        ):
            raise AppProcessError(
                "date precision needs source times and calendar evidence"
            )
        disclosed = field.disclosure_date()
        try:
            boundary, digest, evidence = self._calendar.publication_boundary(disclosed)
        except ValueError as error:
            raise AppProcessError(str(error)) from error
        return replace(
            field,
            date_visible_at=boundary,
            calendar_hash=digest,
            calendar_evidence=evidence,
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

        def selected(checkpoint: PartitionCheckpoint) -> bool:
            return any(
                checkpoint_matches_snapshot(checkpoint, item) for item in snapshots
            )

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
        if not entries or not snapshots:
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
    ) -> None:
        assets = {entry.asset: entry for entry in entries}
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
            if not snapshot_completed(snapshot, self._lifecycle_reader):
                raise AppProcessError("provider snapshot has no COMPLETE checkpoint")

    def _verify_certified_fields(
        self,
        request: CertificationBuildRequest,
        snapshots: tuple[ProviderSnapshot, ...],
        entries: tuple[DataCatalogEntry, ...],
    ) -> None:
        """Require unique claims grounded in the exact catalog schema."""
        if len(
            {(field.field, field.snapshot_id) for field in request.certified_fields}
        ) != len(request.certified_fields):
            raise AppProcessError("certified field claims must be unique per snapshot")
        snapshot_assets = {item.snapshot_id: item.canonical_asset for item in snapshots}
        for field in request.certified_fields:
            matching = [
                entry
                for entry in entries
                if entry.asset == snapshot_assets.get(field.snapshot_id)
            ]
            if not matching or not all(
                field.field in entry.schema.columns for entry in matching
            ):
                raise AppProcessError(
                    "certified field is absent from the exact catalog schema"
                )
            if field.evidence_uri != request.consumer_evidence.evidence_uri:
                raise AppProcessError(
                    "certified field must reference verified consumer evidence"
                )

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


def _verify_consumer_bindings(request: CertificationBuildRequest) -> None:
    """Require every input digest to match retained, hash-verified consumer facts."""
    expected = {
        binding
        for field in request.certified_fields
        for binding in field.consumer_bindings
    }
    if not expected:
        return
    request.consumer_evidence.verify()
    try:
        payload: object = orjson.loads(
            request.consumer_evidence.local_path.read_bytes()
        )
    except (OSError, ValueError) as exc:
        raise AppProcessError("consumer evidence is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise AppProcessError("consumer evidence must be an object")
    inputs = cast(dict[str, object], payload).get("field_inputs")
    if not isinstance(inputs, list):
        raise AppProcessError("consumer evidence has no retained field inputs")
    actual: set[tuple[str, str]] = set()
    for item in cast(list[object], inputs):
        if not isinstance(item, dict):
            raise AppProcessError("consumer field input must be an object")
        record = cast(dict[str, object], item)
        name = record.get("consumer_field")
        if not isinstance(name, str):
            raise AppProcessError("consumer field input name is required")
        actual.add((name, consumer_input_digest(record)))
    if not expected.issubset(actual):
        raise AppProcessError("consumer input binding does not match retained evidence")
