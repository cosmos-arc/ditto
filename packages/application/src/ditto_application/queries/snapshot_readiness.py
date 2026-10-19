"""
Minimal data consumability checks over durable snapshot ledgers.

This replaces the former field-admission gate's non-governance half: exact
content identity, ingestion completion, payload retention and request-scope
coverage. Temporal visibility stays with the consumers' own row-level PIT
filters; licenses and certifications no longer participate.

Date-partitioned datasets are covered at union granularity on the assess
path: backfilled stores stitch month, week and single-day snapshots, so the
request window must sit inside the union of the declared snapshots'
intervals, never inside any single one. Whole-snapshot consumers
(``snapshot_reasons``) keep single-snapshot containment. Union coverage
attests the declared set as a whole: each snapshot still serves rows only
within its own interval, and bar-shaped consumers keep their row-level
per-date backstops (the selection lane's assembly coverage check).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from itertools import pairwise
from typing import Protocol

from ditto_data.catalog.metadata import default_dataset_metadata
from ditto_data.catalog.snapshot_completion import snapshot_completed
from ditto_data.catalog.source_snapshot import ProviderSnapshot, ProviderSnapshotReader
from ditto_data.ingestion.partition_state import PartitionLifecycleReader

from ditto_application.catalog_freshness import observed_snapshot_ids
from ditto_application.exceptions import AppQueryError

__all__ = [
    "FieldRequirement",
    "SnapshotReadiness",
    "SnapshotReadinessQuery",
    "SnapshotReadinessReport",
    "SnapshotReadinessRequest",
]

_DAY = timedelta(days=1)


class _IntervalStamped(Protocol):
    """Snapshots and partition checkpoints both carry an ISO request interval."""

    @property
    def request_start(self) -> str: ...

    @property
    def request_end(self) -> str: ...


def _interval(record: _IntervalStamped) -> tuple[date, date]:
    return (
        date.fromisoformat(record.request_start),
        date.fromisoformat(record.request_end),
    )


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

    def observed_snapshot_ids(
        self, *, dataset_ids: tuple[str, ...], knowledge_cutoff: datetime
    ) -> tuple[str, ...]:
        """Resolve completed, cutoff-visible identities for application consumers."""
        return observed_snapshot_ids(
            self._snapshots,
            self._lifecycle,
            dataset_ids=dataset_ids,
            knowledge_cutoff=knowledge_cutoff,
        )

    def assess(self, request: SnapshotReadinessRequest) -> SnapshotReadinessReport:
        """Assess exact snapshots without ingestion or certification writes."""
        snapshots: dict[str, ProviderSnapshot | None] = {}
        reasons_by_snapshot: dict[str, tuple[str, ...]] = {}
        for item in request.fields:
            if item.snapshot_id not in reasons_by_snapshot:
                snapshots[item.snapshot_id] = self._snapshots.get_snapshot(
                    item.snapshot_id
                )
                reasons_by_snapshot[item.snapshot_id] = self._base_reasons(
                    item, snapshots[item.snapshot_id]
                )
        uncovered = self._uncovered_datasets(request, snapshots)
        fields = tuple(
            SnapshotReadiness(
                dataset_id=item.dataset_id,
                field=item.field,
                snapshot_id=item.snapshot_id,
                consumer_field=item.consumer_field,
                reason_codes=(
                    *reasons_by_snapshot[item.snapshot_id],
                    *(
                        ("SNAPSHOT_COVERAGE_MISSING",)
                        if item.dataset_id in uncovered
                        else ()
                    ),
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
        if required_from > required_to:
            raise AppQueryError("snapshot readiness interval is reversed")
        snapshot = self._snapshots.get_snapshot(snapshot_id)
        item = FieldRequirement(dataset_id, "", snapshot_id)
        reasons = self._base_reasons(item, snapshot)
        if snapshot is None or snapshot.dataset_id != dataset_id:
            return reasons
        if self._date_partitioned(dataset_id) and (
            required_from < date.fromisoformat(snapshot.request_start)
            or required_to > date.fromisoformat(snapshot.request_end)
        ):
            # Whole-snapshot consumers must sit inside the one snapshot's
            # own interval; union coverage is an assess-path semantic.
            return (*reasons, "SNAPSHOT_COVERAGE_MISSING")
        return reasons

    def _base_reasons(
        self, item: FieldRequirement, snapshot: ProviderSnapshot | None
    ) -> tuple[str, ...]:
        if snapshot is None:
            return ("SNAPSHOT_MISSING",)
        if snapshot.dataset_id != item.dataset_id:
            return ("SNAPSHOT_CONFLICT",)
        reasons: list[str] = []
        if not snapshot_completed(snapshot, self._lifecycle):
            reasons.append("SNAPSHOT_INCOMPLETE")
        if not snapshot.payload_retained:
            reasons.append("SNAPSHOT_PAYLOAD_MISSING")
        return tuple(reasons)

    def _date_partitioned(self, dataset_id: str) -> bool:
        spec = default_dataset_metadata().get(dataset_id)
        return bool(
            spec
            and spec.dataset_spec
            and spec.dataset_spec.partition_keys == ("trade_date",)
        )

    def _uncovered_datasets(
        self,
        request: SnapshotReadinessRequest,
        snapshots: Mapping[str, ProviderSnapshot | None],
    ) -> frozenset[str]:
        """
        Date-partitioned datasets must cover the window by declared union.

        Roster/observation-keyed snapshots (e.g. knowledge_date) state a
        point-in-time fact with no interval semantics: completion and
        retention already attested per snapshot, and time visibility belongs
        to the caller's cutoff — no coverage reason applies.
        """
        by_dataset: dict[str, list[ProviderSnapshot]] = {}
        for item in request.fields:
            snapshot = snapshots.get(item.snapshot_id)
            if (
                self._date_partitioned(item.dataset_id)
                and snapshot is not None
                and snapshot.dataset_id == item.dataset_id
            ):
                by_dataset.setdefault(item.dataset_id, []).append(snapshot)
        return frozenset(
            dataset_id
            for dataset_id, group in by_dataset.items()
            if self._union_uncovered(
                dataset_id, group, request.required_from, request.required_to
            )
        )

    def _union_uncovered(
        self,
        dataset_id: str,
        group: list[ProviderSnapshot],
        required_from: date,
        required_to: date,
    ) -> bool:
        """
        True when the declared snapshots' interval union cannot serve the window.

        The window edges must sit inside declared intervals. Calendar gaps
        between stitched blocks are real holes only when partition lifecycle
        shows ingestion claimed those days (a pending or completed chunk the
        request did not declare); ranges no chunk claims are non-trading
        spans the calendar-free query layer must bridge.
        """
        merged: list[list[date]] = []
        for start, end in sorted(_interval(item) for item in group):
            if merged and start <= merged[-1][1]:
                merged[-1][1] = max(merged[-1][1], end)
            else:
                merged.append([start, end])
        if not any(start <= required_from <= end for start, end in merged):
            return True
        if not any(start <= required_to <= end for start, end in merged):
            return True
        holes = [
            (max(prev_end + _DAY, required_from), min(next_start - _DAY, required_to))
            for (_, prev_end), (next_start, _) in pairwise(merged)
        ]
        holes = [(start, end) for start, end in holes if start <= end]
        if not holes:
            return False
        claims = tuple(
            _interval(checkpoint)
            for checkpoint in (
                *self._lifecycle.list_incomplete(dataset_id=dataset_id),
                *self._lifecycle.list_complete(dataset_id=dataset_id),
            )
        )
        return any(
            claim_start <= hole_end and hole_start <= claim_end
            for hole_start, hole_end in holes
            for claim_start, claim_end in claims
        )
