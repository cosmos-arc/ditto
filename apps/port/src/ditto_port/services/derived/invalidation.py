"""Port-side invalidation fan-out and repair orchestration."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from ditto_core.engine.materialization import (
    DerivedInvalidationEvent,
    DerivedMaterializationRequest,
    DerivedMaterializationResult,
)
from ditto_core.engine.materialization.models import DerivedRunMode, DerivedRunTrigger
from ditto_datahub.models.derived import DerivedInvalidationRecord
from ditto_datahub.services.derived_catalog_service import DerivedCatalogService

from ditto_port.services.derived.materialization_orchestrator import (
    DerivedMaterializationOrchestrator,
)

__all__ = ["DerivedInvalidationOrchestrator"]


class DerivedInvalidationOrchestrator:
    """Expand invalidations across dependency edges and repair pending work."""

    def __init__(
        self,
        *,
        catalog_service: DerivedCatalogService,
        materialization_service: DerivedMaterializationOrchestrator,
    ) -> None:
        self._catalog_service = catalog_service
        self._materialization_service = materialization_service

    def enqueue(self, event: DerivedInvalidationEvent) -> str:
        """Create pending invalidations for durable downstream specs."""
        created_at = datetime.now(UTC).isoformat()
        records: list[DerivedInvalidationRecord] = []
        for dependency in self._catalog_service.list_dependencies_by_ref(
            event.root_dependency_ref
        ):
            spec = self._catalog_service.get_spec(
                dependency.derived_id,
                dependency.version,
            )
            if spec is None or spec.materialization_profile == "DERIVE":
                continue
            records.append(
                DerivedInvalidationRecord(
                    invalidation_id=f"inval-{uuid4().hex[:12]}",
                    derived_id=dependency.derived_id,
                    version=dependency.version,
                    source_domain=event.source_domain,
                    source_dataset=event.source_dataset,
                    change_date=event.change_date,
                    affected_start=event.affected_start,
                    affected_end=event.affected_end,
                    source_snapshot_id=event.source_snapshot_id,
                    root_dependency_ref=event.root_dependency_ref,
                    status="pending",
                    created_at=created_at,
                    processed_at=None,
                )
            )
        if not records:
            records.append(
                DerivedInvalidationRecord(
                    invalidation_id=f"inval-{uuid4().hex[:12]}",
                    derived_id=event.root_dependency_ref,
                    version=0,
                    source_domain=event.source_domain,
                    source_dataset=event.source_dataset,
                    change_date=event.change_date,
                    affected_start=event.affected_start,
                    affected_end=event.affected_end,
                    source_snapshot_id=event.source_snapshot_id,
                    root_dependency_ref=event.root_dependency_ref,
                    status="pending",
                    created_at=created_at,
                    processed_at=None,
                )
            )
        self._catalog_service.save_invalidations(tuple(records))
        return records[0].invalidation_id

    def repair_pending(self, limit: int) -> tuple[DerivedMaterializationResult, ...]:
        """Repair pending invalidations in creation order."""
        results: list[DerivedMaterializationResult] = []
        processed_at = datetime.now(UTC).isoformat()
        for invalidation in self._catalog_service.list_pending_invalidations()[:limit]:
            if invalidation.version == 0:
                self._catalog_service.mark_invalidation_processed(
                    invalidation.invalidation_id,
                    processed_at,
                )
                continue
            results.append(
                self._materialization_service.materialize(
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
            )
            self._catalog_service.mark_invalidation_processed(
                invalidation.invalidation_id,
                processed_at,
            )
        return tuple(results)
