"""
Invalidation cascade protocol with BFS propagation and state machine.

I-CASC-01: BFS multi-level propagation
I-CASC-02: State machine (fresh -> stale -> recomputing -> healed)
I-CASC-03: Cycle guard + micro-batch merge + max depth
"""

from __future__ import annotations

from collections import deque
from datetime import UTC, datetime
from enum import StrEnum
from uuid import uuid4

from ditto_core.engine.materialization import (
    DerivedInvalidationEvent,
    DerivedMaterializationRequest,
    DerivedMaterializationResult,
)
from ditto_core.engine.materialization.models import DerivedRunMode, DerivedRunTrigger
from ditto_datahub.models.derived import DerivedInvalidationRecord
from ditto_datahub.services.derived_catalog_service import DerivedCatalogService
from loguru import logger

from ditto_port.services.derived.materialization_orchestrator import (
    DerivedMaterializationOrchestrator,
)

__all__ = [
    "REALTIME_CASCADE_MAX_DEPTH",
    "CascadeDepthExceededError",
    "CascadeStatus",
    "InvalidationCascadeOrchestrator",
]


class CascadeStatus(StrEnum):
    """Cascade propagation lifecycle status."""

    FRESH = "fresh"
    STALE = "stale"
    RECOMPUTING = "recomputing"
    HEALED = "healed"


class CascadeDepthExceededError(Exception):
    """Raised when cascade propagation exceeds the configured max depth."""

    def __init__(self, derived_id: str, depth: int) -> None:
        self.derived_id = derived_id
        self.depth = depth
        super().__init__(f"cascade depth exceeded for {derived_id}: depth={depth}")


REALTIME_CASCADE_MAX_DEPTH = 5


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

            # Create stale invalidation record for this node
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
    ) -> tuple[DerivedMaterializationResult, ...]:
        """
        Repair stale invalidations in depth order.

        Transitions each record through: stale -> recomputing -> healed.
        On failure, reverts to stale and raises.

        Returns:
            Tuple of materialization results for successfully repaired items.

        """
        results: list[DerivedMaterializationResult] = []

        # Already sorted by depth then created_at from catalog service
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
            except Exception:
                # State transition: recomputing -> stale (failure revert)
                self._catalog_service.mark_invalidation_status(
                    invalidation.invalidation_id,
                    CascadeStatus.STALE,
                )
                raise

        return tuple(results)

    def _emit_depth_alert(self, derived_id: str, depth: int) -> None:
        """Log a warning when cascade depth is exceeded."""
        logger.warning(
            "cascade depth exceeded for {}: depth={} > max_depth={}",
            derived_id,
            depth,
            self._max_depth,
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
                merged[key] = DerivedInvalidationRecord(
                    invalidation_id=existing.invalidation_id,
                    derived_id=existing.derived_id,
                    version=existing.version,
                    source_domain=existing.source_domain,
                    source_dataset=existing.source_dataset,
                    change_date=existing.change_date,
                    affected_start=min(existing.affected_start, record.affected_start),
                    affected_end=max(existing.affected_end, record.affected_end),
                    source_snapshot_id=existing.source_snapshot_id,
                    root_dependency_ref=existing.root_dependency_ref,
                    status=existing.status,
                    created_at=existing.created_at,
                    processed_at=existing.processed_at,
                    depth=existing.depth,
                )
        return list(merged.values())
