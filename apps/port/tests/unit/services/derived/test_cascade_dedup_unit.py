"""Unit tests for INVAL-IC-4: cross-event deduplication (subsumed healing)."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock
from uuid import uuid4

from ditto_core.engine.materialization import DerivedMaterializationResult
from ditto_core.engine.materialization.models import (
    DerivedRunStatus,
)
from ditto_core.engine.specs import MaterializationProfile
from ditto_datahub.models.derived import DerivedInvalidationRecord
from ditto_port.services.derived.cascade_protocol import (
    CascadeStatus,
    InvalidationCascadeOrchestrator,
)


def _make_record(
    *,
    derived_id: str = "factor.downstream",
    version: int = 1,
    status: str = CascadeStatus.STALE,
    depth: int = 0,
    affected_start: str = "2026-03-10",
    affected_end: str = "2026-03-11",
    retry_count: int = 0,
    role: str = "factor",
) -> DerivedInvalidationRecord:
    return DerivedInvalidationRecord(
        invalidation_id=f"inval-{uuid4().hex[:12]}",
        derived_id=derived_id,
        version=version,
        source_domain="market",
        source_dataset="stock_daily",
        change_date="2026-03-11",
        affected_start=affected_start,
        affected_end=affected_end,
        source_snapshot_id=None,
        root_dependency_ref="factor.alpha_upstream",
        status=status,
        created_at=datetime.now(UTC).isoformat(),
        processed_at=None,
        depth=depth,
        retry_count=retry_count,
        role=role,
    )


def _make_materialization_result(
    derived_id: str = "test",
) -> DerivedMaterializationResult:
    return DerivedMaterializationResult(
        run_id="run-001",
        derived_id=derived_id,
        version=1,
        profile=MaterializationProfile.SERIES,
        status=DerivedRunStatus.SUCCESS,
        rows_written=1,
        partitions_written=("2026-03-10",),
        coverage_start="2026-03-10",
        coverage_end="2026-03-11",
    )


class TestMarkSubsumedHealed:
    """INAL-IC-4: _mark_subsumed_healed marks subsumed stale records as healed."""

    def test_subset_range_auto_healed(self) -> None:
        """Stale [5,10] is healed when another repair covers [1,20]."""
        catalog_service = MagicMock()
        materialization_service = MagicMock()

        # The record being repaired has a wide range [1,20]
        repaired_record = _make_record(
            derived_id="factor.downstream",
            version=1,
            affected_start="2026-03-01",
            affected_end="2026-03-20",
            depth=0,
        )
        catalog_service.list_stale_invalidations.return_value = (repaired_record,)

        materialization_service.materialize.return_value = _make_materialization_result(
            derived_id="factor.downstream",
        )

        # A stale record for same derived_id:version with subset range [5,10]
        subsumed_record = _make_record(
            derived_id="factor.downstream",
            version=1,
            affected_start="2026-03-05",
            affected_end="2026-03-10",
            depth=1,
        )
        catalog_service.list_stale_by_derived_version.return_value = (subsumed_record,)

        cascade = InvalidationCascadeOrchestrator(
            catalog_service=catalog_service,
            materialization_service=materialization_service,
        )

        cascade.repair_batch(batch_size=10)

        # After successful repair, _mark_subsumed_healed should be called
        # list_stale_by_derived_version should be queried for same derived_id:version
        catalog_service.list_stale_by_derived_version.assert_called_once_with(
            "factor.downstream",
            1,
        )

        # The subsumed record should be marked healed
        catalog_service.mark_invalidation_status.assert_any_call(
            subsumed_record.invalidation_id,
            CascadeStatus.HEALED,
        )

    def test_partial_overlap_not_auto_healed(self) -> None:
        """Stale record [5,20] is NOT healed by [1,10] (partial overlap)."""
        catalog_service = MagicMock()
        materialization_service = MagicMock()

        # The repaired record has range [1,10]
        repaired_record = _make_record(
            derived_id="factor.downstream",
            version=1,
            affected_start="2026-03-01",
            affected_end="2026-03-10",
            depth=0,
        )
        catalog_service.list_stale_invalidations.return_value = (repaired_record,)

        materialization_service.materialize.return_value = _make_materialization_result(
            derived_id="factor.downstream",
        )

        # Stale record with range [5,20] - NOT a subset of [1,10]
        non_subsumed_record = _make_record(
            derived_id="factor.downstream",
            version=1,
            affected_start="2026-03-05",
            affected_end="2026-03-20",
            depth=1,
        )
        catalog_service.list_stale_by_derived_version.return_value = (
            non_subsumed_record,
        )

        cascade = InvalidationCascadeOrchestrator(
            catalog_service=catalog_service,
            materialization_service=materialization_service,
        )

        cascade.repair_batch(batch_size=10)

        # The non-subsumed record should NOT be marked healed
        mark_calls = catalog_service.mark_invalidation_status.call_args_list
        healed_ids = [c[0][0] for c in mark_calls if c[0][1] == CascadeStatus.HEALED]
        assert non_subsumed_record.invalidation_id not in healed_ids

    def test_different_version_not_affected(self) -> None:
        """Healing v1 queries list_stale_by_derived_version with version=1 only."""
        catalog_service = MagicMock()
        materialization_service = MagicMock()

        # Repair v1 record
        repaired_record = _make_record(
            derived_id="factor.downstream",
            version=1,
            affected_start="2026-03-01",
            affected_end="2026-03-20",
            depth=0,
        )
        catalog_service.list_stale_invalidations.return_value = (repaired_record,)

        materialization_service.materialize.return_value = _make_materialization_result(
            derived_id="factor.downstream",
        )

        # The reader would only return v1 stale records when queried with version=1.
        # A v2 record is invisible to this query.
        catalog_service.list_stale_by_derived_version.return_value = ()

        cascade = InvalidationCascadeOrchestrator(
            catalog_service=catalog_service,
            materialization_service=materialization_service,
        )

        cascade.repair_batch(batch_size=10)

        # list_stale_by_derived_version should be called with version=1, not version=2
        catalog_service.list_stale_by_derived_version.assert_called_once_with(
            "factor.downstream",
            1,
        )

        # No additional healed calls beyond the repaired record itself
        mark_calls = catalog_service.mark_invalidation_status.call_args_list
        healed_calls = [c for c in mark_calls if c[0][1] == CascadeStatus.HEALED]
        assert len(healed_calls) == 1
        assert healed_calls[0][0][0] == repaired_record.invalidation_id

    def test_exact_match_auto_healed(self) -> None:
        """Stale record [5,10] healed by exactly [5,10]."""
        catalog_service = MagicMock()
        materialization_service = MagicMock()

        repaired_record = _make_record(
            derived_id="factor.downstream",
            version=1,
            affected_start="2026-03-05",
            affected_end="2026-03-10",
            depth=0,
        )
        catalog_service.list_stale_invalidations.return_value = (repaired_record,)

        materialization_service.materialize.return_value = _make_materialization_result(
            derived_id="factor.downstream",
        )

        # Exact same range
        exact_match_record = _make_record(
            derived_id="factor.downstream",
            version=1,
            affected_start="2026-03-05",
            affected_end="2026-03-10",
            depth=1,
        )
        catalog_service.list_stale_by_derived_version.return_value = (
            exact_match_record,
        )

        cascade = InvalidationCascadeOrchestrator(
            catalog_service=catalog_service,
            materialization_service=materialization_service,
        )

        cascade.repair_batch(batch_size=10)

        # The exact-match record should be marked healed
        mark_calls = catalog_service.mark_invalidation_status.call_args_list
        healed_ids = [c[0][0] for c in mark_calls if c[0][1] == CascadeStatus.HEALED]
        assert exact_match_record.invalidation_id in healed_ids

    def test_no_subsumable_records(self) -> None:
        """No stale records to subsume -> no calls to mark healed for subsumed."""
        catalog_service = MagicMock()
        materialization_service = MagicMock()

        repaired_record = _make_record(
            derived_id="factor.downstream",
            version=1,
            affected_start="2026-03-01",
            affected_end="2026-03-20",
            depth=0,
        )
        catalog_service.list_stale_invalidations.return_value = (repaired_record,)

        materialization_service.materialize.return_value = _make_materialization_result(
            derived_id="factor.downstream",
        )

        # No stale records for this derived_id:version
        catalog_service.list_stale_by_derived_version.return_value = ()

        cascade = InvalidationCascadeOrchestrator(
            catalog_service=catalog_service,
            materialization_service=materialization_service,
        )

        cascade.repair_batch(batch_size=10)

        # list_stale_by_derived_version should still be called
        catalog_service.list_stale_by_derived_version.assert_called_once_with(
            "factor.downstream",
            1,
        )

        # Only the repaired record itself should be healed, no extras
        mark_calls = catalog_service.mark_invalidation_status.call_args_list
        healed_calls = [c for c in mark_calls if c[0][1] == CascadeStatus.HEALED]
        # One for the repaired record itself
        assert len(healed_calls) == 1
        assert healed_calls[0][0][0] == repaired_record.invalidation_id
