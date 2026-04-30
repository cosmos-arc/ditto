"""
Invalidation cascade protocol with BFS propagation and state machine.

I-CASC-01: BFS multi-level propagation
I-CASC-02: State machine (fresh -> stale -> recomputing -> healed)
I-CASC-03: Cycle guard + micro-batch merge + max depth
INVAL-IC-1: repair_batch failure resilience
INVAL-IC-2: Dead letter queue
INVAL-IC-3: Priority queue ordering
INVAL-IC-4: Cross-event deduplication (subsumed healing)
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum
from uuid import uuid4

from ditto_data.models.derived import DerivedInvalidationRecord
from ditto_data.services import DerivedCatalogService
from ditto_features.materialization import (
    DerivedInvalidationEvent,
    DerivedMaterializationRequest,
    DerivedMaterializationResult,
    DerivedRunMode,
    DerivedRunTrigger,
)
from ditto_platform.foundation import logger

from ditto_application.exceptions import AppError
from ditto_application.process.materialization.orchestrator import (
    DerivedMaterializationOrchestrator,
)

__all__ = [
    "CASCADE_MAX_RETRY_COUNT",
    "REALTIME_CASCADE_MAX_DEPTH",
    "CascadeDepthExceededError",
    "CascadeStatus",
    "InvalidationCascadeOrchestrator",
    "RepairBatchResult",
]


class CascadeStatus(StrEnum):
    """Cascade propagation lifecycle status."""

    FRESH = "fresh"
    STALE = "stale"
    RECOMPUTING = "recomputing"
    HEALED = "healed"
    DEAD_LETTER = "dead_letter"


class CascadeDepthExceededError(AppError):
    """Raised when cascade propagation exceeds the configured max depth."""

    def __init__(self, derived_id: str, depth: int) -> None:
        self.derived_id = derived_id
        self.depth = depth
        super().__init__(f"cascade depth exceeded for {derived_id}: depth={depth}")


REALTIME_CASCADE_MAX_DEPTH = 5
CASCADE_MAX_RETRY_COUNT = 3


@dataclass(frozen=True)
class RepairBatchResult:
    """Result of a repair batch operation containing successes and failures."""

    repaired: tuple[DerivedMaterializationResult, ...]
    failed: tuple[str, ...]


class InvalidationCascadeOrchestrator:
    """
    BFS-based invalidation cascade with cycle guard and state machine.

    Orchestrates invalidation propagation through the derived dependency
    graph using breadth-first search, tracking depth and detecting cycles
    via a visited set. Coordinates catalog service and materialization
    service for batch repair of stale derived artifacts.
    """

    def __init__(
        self,
        *,
        catalog_service: DerivedCatalogService,
        materialization_service: DerivedMaterializationOrchestrator,
        max_depth: int = REALTIME_CASCADE_MAX_DEPTH,
    ) -> None:
        self._catalog_service = catalog_service
        self._materialization_service = materialization_service
        self._max_depth = max_depth

    def propagate(
        self,
        event: DerivedInvalidationEvent,
    ) -> tuple[str, ...]:
        """
        BFS multi-level propagation of an invalidation event.

        Traverses the dependency graph from the root, creating stale
        invalidation records at each visited node. Deduplicates cycles
        and stops at max_depth.

        Returns:
            Tuple of invalidation IDs created by this propagation.

        """
        created_at = datetime.now(UTC).isoformat()
        all_records: list[DerivedInvalidationRecord] = []
        visited: set[str] = set()

        # BFS queue: (derived_id, version, depth)
        queue: deque[tuple[str, int, int]] = deque()
        queue.append((event.root_dependency_ref, 0, 0))

        while queue:
            current_id, current_version, depth = queue.popleft()

            # Cycle guard
            if current_id in visited:
                logger.warning(
                    "cycle detected in cascade, skipping: derived_id={}",
                    current_id,
                )
                continue
            visited.add(current_id)

            # Depth guard
            if depth > self._max_depth:
                self._emit_depth_alert(current_id, depth)
                continue

            # Skip source domain root refs (e.g. "market.stock_daily")
            # but still traverse downstream deps
            is_source_domain_root = depth == 0 and current_id.startswith(
                f"{event.source_domain}."
            )

            if not is_source_domain_root:
                record = DerivedInvalidationRecord(
                    invalidation_id=f"inval-{uuid4().hex[:12]}",
                    derived_id=current_id,
                    version=current_version,
                    source_domain=event.source_domain,
                    source_dataset=event.source_dataset,
                    change_date=event.change_date,
                    affected_start=event.affected_start,
                    affected_end=event.affected_end,
                    source_snapshot_id=event.source_snapshot_id,
                    root_dependency_ref=event.root_dependency_ref,
                    status=CascadeStatus.STALE,
                    created_at=created_at,
                    processed_at=None,
                    depth=depth,
                    role="factor",
                )
                all_records.append(record)

            # Find downstream dependencies and enqueue
            for dep in self._catalog_service.list_downstream_dependencies(current_id):
                queue.append((dep.derived_id, dep.version, depth + 1))

        # Micro-batch merge: same derived_id:version -> single record
        merged = self._merge_batch_events(all_records)
        self._catalog_service.save_invalidations(tuple(merged))

        return tuple(r.invalidation_id for r in merged)

    def repair_batch(
        self,
        batch_size: int = 10,
    ) -> RepairBatchResult:
        """
        Repair stale invalidations in priority/depth order.

        Transitions each record through: stale -> recomputing -> healed.
        On failure, increments retry count. If retry_count >= max, marks
        as dead letter; otherwise reverts to stale and continues to
        the next item. Never raises due to individual item failures.

        Returns:
            RepairBatchResult with successfully repaired items and failed IDs.

        """
        results: list[DerivedMaterializationResult] = []
        failed_ids: list[str] = []

        # Already sorted by role priority, depth, then created_at
        pending = self._catalog_service.list_stale_invalidations()

        for invalidation in pending[:batch_size]:
            # State transition: stale -> recomputing
            self._catalog_service.mark_invalidation_status(
                invalidation.invalidation_id,
                CascadeStatus.RECOMPUTING,
            )

            try:
                result = self._materialization_service.materialize(
                    DerivedMaterializationRequest(
                        derived_id=invalidation.derived_id,
                        version=invalidation.version,
                        mode=DerivedRunMode.INCREMENTAL,
                        request_start=invalidation.affected_start,
                        request_end=invalidation.affected_end,
                        trigger=DerivedRunTrigger.CASCADE,
                        source_snapshot_id=invalidation.source_snapshot_id,
                    )
                )
                # State transition: recomputing -> healed
                self._catalog_service.mark_invalidation_status(
                    invalidation.invalidation_id,
                    CascadeStatus.HEALED,
                )
                results.append(result)
                # Mark any subsumed stale records as healed
                self._mark_subsumed_healed(
                    healed_id=invalidation.invalidation_id,
                    derived_id=invalidation.derived_id,
                    version=invalidation.version,
                    affected_start=invalidation.affected_start,
                    affected_end=invalidation.affected_end,
                )
            except Exception as exc:
                error_message = str(exc)
                logger.error(
                    "repair failed for {}: {}",
                    invalidation.invalidation_id,
                    error_message,
                )
                new_retry_count = invalidation.retry_count + 1
                self._catalog_service.increment_retry_count(
                    invalidation.invalidation_id,
                )
                if new_retry_count >= CASCADE_MAX_RETRY_COUNT:
                    dead_letter_at = datetime.now(UTC).isoformat()
                    self._catalog_service.mark_invalidation_dead_letter(
                        invalidation.invalidation_id,
                        error_message,
                        dead_letter_at,
                    )
                    logger.warning(
                        "dead-lettered {} after {} retries",
                        invalidation.invalidation_id,
                        new_retry_count,
                    )
                else:
                    # State transition: recomputing -> stale (failure revert)
                    self._catalog_service.mark_invalidation_status(
                        invalidation.invalidation_id,
                        CascadeStatus.STALE,
                    )
                failed_ids.append(invalidation.invalidation_id)

        return RepairBatchResult(
            repaired=tuple(results),
            failed=tuple(failed_ids),
        )

    def _emit_depth_alert(self, derived_id: str, depth: int) -> None:
        """Log a warning when cascade depth is exceeded."""
        logger.warning(
            "cascade depth exceeded for {}: depth={} > max_depth={}",
            derived_id,
            depth,
            self._max_depth,
        )

    def _mark_subsumed_healed(
        self,
        healed_id: str,
        derived_id: str,
        version: int,
        affected_start: str,
        affected_end: str,
    ) -> None:
        """Mark stale records subsumed by a successful repair as healed."""
        stale_records = self._catalog_service.list_stale_by_derived_version(
            derived_id,
            version,
        )
        for record in stale_records:
            if (
                record.invalidation_id == healed_id
                or record.affected_start < affected_start
                or record.affected_end > affected_end
            ):
                continue
            self._catalog_service.mark_invalidation_status(
                record.invalidation_id,
                CascadeStatus.HEALED,
            )

    @staticmethod
    def _merge_batch_events(
        records: list[DerivedInvalidationRecord],
    ) -> list[DerivedInvalidationRecord]:
        """
        Merge records sharing the same derived_id:version key.

        When multiple records target the same derived spec, keeps the
        first occurrence and expands the affected date range to the
        union of all occurrences.
        """
        merged: dict[str, DerivedInvalidationRecord] = {}
        for record in records:
            key = f"{record.derived_id}:{record.version}"
            if key not in merged:
                merged[key] = record
            else:
                existing = merged[key]
                merged[key] = replace(
                    existing,
                    affected_start=min(existing.affected_start, record.affected_start),
                    affected_end=max(existing.affected_end, record.affected_end),
                )
        return list(merged.values())
