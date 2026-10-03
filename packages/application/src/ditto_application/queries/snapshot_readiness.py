"""
Minimal data consumability checks over durable snapshot ledgers.

This replaces the former field-admission gate's non-governance half: exact
content identity, ingestion completion, payload retention and request-scope
coverage. Temporal visibility stays with the consumers' own row-level PIT
filters; licenses and certifications no longer participate.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from ditto_data.catalog.snapshot_completion import snapshot_completed
from ditto_data.catalog.source_snapshot import ProviderSnapshotReader
from ditto_data.ingestion.partition_state import PartitionLifecycleReader

from ditto_application.exceptions import AppQueryError

__all__ = [
    "FieldRequirement",
    "SnapshotReadiness",
    "SnapshotReadinessQuery",
    "SnapshotReadinessReport",
    "SnapshotReadinessRequest",
]


@dataclass(frozen=True, slots=True)
class FieldRequirement:
    """Exact field and snapshot one consumer actually depends on."""

    dataset_id: str
    field: str
    snapshot_id: str
    consumer_field: str = ""


@dataclass(frozen=True, slots=True)
class SnapshotReadinessRequest:
    """Shared request scope for every required input field."""

    fields: tuple[FieldRequirement, ...]
    required_from: date
    required_to: date

    def __post_init__(self) -> None:
        """Fail closed on ambiguous or empty input scopes."""
        if self.required_from > self.required_to:
            raise AppQueryError("snapshot readiness interval is reversed")
        if not self.fields:
            raise AppQueryError("snapshot readiness requires fields")


@dataclass(frozen=True, slots=True)
class SnapshotReadiness:
    """Addressed findings for one actual consumer dependency."""

    dataset_id: str
    field: str
    snapshot_id: str
    consumer_field: str
    reason_codes: tuple[str, ...]

    @property
    def ready(self) -> bool:
        """A dependency is ready when no consumability reason fired."""
        return not self.reason_codes


@dataclass(frozen=True, slots=True)
class SnapshotReadinessReport:
    """Data qualification only; strategy validation remains separate."""

    ready: bool
    fields: tuple[SnapshotReadiness, ...]
    rule_version: str = "snapshot-readiness-v1"


class SnapshotReadinessQuery:
    """Qualify exact snapshots against their own ingestion evidence."""

    def __init__(
        self,
        snapshots: ProviderSnapshotReader,
        lifecycle: PartitionLifecycleReader,
    ) -> None:
        self._snapshots = snapshots
        self._lifecycle = lifecycle

    def assess(self, request: SnapshotReadinessRequest) -> SnapshotReadinessReport:
        """Assess exact snapshots without ingestion or certification writes."""
        reasons_by_snapshot: dict[str, tuple[str, ...]] = {}
        fields = tuple(
            SnapshotReadiness(
                dataset_id=item.dataset_id,
                field=item.field,
                snapshot_id=item.snapshot_id,
                consumer_field=item.consumer_field,
                reason_codes=reasons_by_snapshot.setdefault(
                    item.snapshot_id,
                    self._snapshot_reasons(item, request),
                ),
            )
            for item in request.fields
        )
        return SnapshotReadinessReport(
            ready=all(item.ready for item in fields),
            fields=fields,
        )

    def snapshot_reasons(
        self,
        dataset_id: str,
        snapshot_id: str,
        required_from: date,
        required_to: date,
    ) -> tuple[str, ...]:
        """Qualify one snapshot directly for whole-snapshot consumers."""
        return self._snapshot_reasons(
            FieldRequirement(dataset_id, "", snapshot_id),
            SnapshotReadinessRequest(
                fields=(FieldRequirement(dataset_id, "", snapshot_id),),
                required_from=required_from,
                required_to=required_to,
            ),
        )

    def _snapshot_reasons(
        self, item: FieldRequirement, request: SnapshotReadinessRequest
    ) -> tuple[str, ...]:
        snapshot = self._snapshots.get_snapshot(item.snapshot_id)
        if snapshot is None:
            return ("SNAPSHOT_MISSING",)
        if snapshot.dataset_id != item.dataset_id:
            return ("SNAPSHOT_CONFLICT",)
        reasons: list[str] = []
        if not snapshot_completed(snapshot, self._lifecycle):
            reasons.append("SNAPSHOT_INCOMPLETE")
        if not snapshot.payload_retained:
            reasons.append("SNAPSHOT_PAYLOAD_MISSING")
        if request.required_from < date.fromisoformat(
            snapshot.request_start
        ) or request.required_to > date.fromisoformat(snapshot.request_end):
            reasons.append("SNAPSHOT_COVERAGE_MISSING")
        return tuple(reasons)
