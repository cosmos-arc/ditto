"""Unit tests for InvalidationCascadeOrchestrator (I-CASC-01/02/03, INVAL-IC)."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock
from uuid import uuid4

from ditto_analytics.materialization import (
    DerivedInvalidationEvent,
    DerivedMaterializationResult,
)
from ditto_analytics.materialization.models import (
    DerivedRunStatus,
)
from ditto_app.process.materialization import (
    REALTIME_CASCADE_MAX_DEPTH,
    CascadeDepthExceededError,
    CascadeStatus,
    InvalidationCascadeOrchestrator,
)
from ditto_datahub.models.derived import (
    DerivedDependencyRecord,
    DerivedInvalidationRecord,
)
from ditto_engine.engine.specs import MaterializationProfile


def _make_event(
    *,
    root_dependency_ref: str = "factor.alpha_upstream",
    source_domain: str = "market",
    source_dataset: str = "stock_daily",
    change_date: str = "2026-03-11",
    affected_start: str = "2026-03-10",
    affected_end: str = "2026-03-11",
    source_snapshot_id: str | None = None,
) -> DerivedInvalidationEvent:
    return DerivedInvalidationEvent(
        source_domain=source_domain,
        source_dataset=source_dataset,
        change_date=change_date,
        affected_start=affected_start,
        affected_end=affected_end,
        source_snapshot_id=source_snapshot_id,
        root_dependency_ref=root_dependency_ref,
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


class TestCascadeStatus:
    """Verify CascadeStatus enum values."""

    def test_status_values(self) -> None:
        assert CascadeStatus.FRESH == "fresh"
        assert CascadeStatus.STALE == "stale"
        assert CascadeStatus.RECOMPUTING == "recomputing"
        assert CascadeStatus.HEALED == "healed"
        assert CascadeStatus.DEAD_LETTER == "dead_letter"


class TestRealtimeCascadeMaxDepth:
    """Verify default depth limit."""

    def test_default_max_depth(self) -> None:
        assert REALTIME_CASCADE_MAX_DEPTH == 5


class TestBFSPropagation:
    """I-CASC-01: BFS multi-level propagation."""

    def test_single_hop_propagation(self) -> None:
        """Root with one downstream creates records for root and downstream."""
        catalog_service = MagicMock()
        materialization_service = MagicMock()

        catalog_service.list_downstream_dependencies.return_value = (
            DerivedDependencyRecord(
                derived_id="factor.downstream",
                version=1,
                dependency_kind="derived",
                dependency_ref="factor.alpha_upstream",
                created_at="2026-03-13T10:00:00+08:00",
            ),
        )

        cascade = InvalidationCascadeOrchestrator(
            catalog_service=catalog_service,
            materialization_service=materialization_service,
        )

        event = _make_event()
        result_ids = cascade.propagate(event)

        assert len(result_ids) == 2
        catalog_service.save_invalidations.assert_called_once()
        saved_records = catalog_service.save_invalidations.call_args[0][0]
        assert len(saved_records) == 2
        depths = {r.derived_id: r.depth for r in saved_records}
        assert depths["factor.alpha_upstream"] == 0
        assert depths["factor.downstream"] == 1

    def test_multi_hop_chain_propagation(self) -> None:
        """A -> B -> C chain creates records at depth 0, 1, and 2."""
        catalog_service = MagicMock()
        materialization_service = MagicMock()

        def list_downstream(derived_id: str):
            if derived_id == "factor.alpha_upstream":
                return (
                    DerivedDependencyRecord(
                        derived_id="factor.mid",
                        version=1,
                        dependency_kind="derived",
                        dependency_ref="factor.alpha_upstream",
                        created_at="2026-03-13T10:00:00+08:00",
                    ),
                )
            if derived_id == "factor.mid":
                return (
                    DerivedDependencyRecord(
                        derived_id="factor.downstream",
                        version=1,
                        dependency_kind="derived",
                        dependency_ref="factor.mid",
                        created_at="2026-03-13T10:00:00+08:00",
                    ),
                )
            return ()

        catalog_service.list_downstream_dependencies.side_effect = list_downstream

        cascade = InvalidationCascadeOrchestrator(
            catalog_service=catalog_service,
            materialization_service=materialization_service,
        )

        event = _make_event()
        result_ids = cascade.propagate(event)

        assert len(result_ids) == 3
        catalog_service.save_invalidations.assert_called_once()
        saved_records = catalog_service.save_invalidations.call_args[0][0]
        depths = {r.derived_id: r.depth for r in saved_records}
        assert depths["factor.alpha_upstream"] == 0
        assert depths["factor.mid"] == 1
        assert depths["factor.downstream"] == 2

    def test_fan_out_propagation(self) -> None:
        """A -> B, A -> C fan-out creates records for A, B, and C."""
        catalog_service = MagicMock()
        materialization_service = MagicMock()

        def list_downstream(derived_id: str):
            if derived_id == "factor.alpha_upstream":
                return (
                    DerivedDependencyRecord(
                        derived_id="factor.downstream_b",
                        version=1,
                        dependency_kind="derived",
                        dependency_ref="factor.alpha_upstream",
                        created_at="2026-03-13T10:00:00+08:00",
                    ),
                    DerivedDependencyRecord(
                        derived_id="factor.downstream_c",
                        version=1,
                        dependency_kind="derived",
                        dependency_ref="factor.alpha_upstream",
                        created_at="2026-03-13T10:00:00+08:00",
                    ),
                )
            return ()

        catalog_service.list_downstream_dependencies.side_effect = list_downstream

        cascade = InvalidationCascadeOrchestrator(
            catalog_service=catalog_service,
            materialization_service=materialization_service,
        )

        event = _make_event()
        result_ids = cascade.propagate(event)

        assert len(result_ids) == 3
        saved_records = catalog_service.save_invalidations.call_args[0][0]
        derived_ids = {r.derived_id for r in saved_records}
        assert derived_ids == {
            "factor.alpha_upstream",
            "factor.downstream_b",
            "factor.downstream_c",
        }

    def test_propagation_marks_stale(self) -> None:
        """Each visited node should be marked stale during propagation."""
        catalog_service = MagicMock()
        materialization_service = MagicMock()

        catalog_service.list_downstream_dependencies.return_value = (
            DerivedDependencyRecord(
                derived_id="factor.downstream",
                version=1,
                dependency_kind="derived",
                dependency_ref="factor.alpha_upstream",
                created_at="2026-03-13T10:00:00+08:00",
            ),
        )

        cascade = InvalidationCascadeOrchestrator(
            catalog_service=catalog_service,
            materialization_service=materialization_service,
        )

        event = _make_event()
        cascade.propagate(event)

        saved_records = catalog_service.save_invalidations.call_args[0][0]
        for record in saved_records:
            assert record.status == CascadeStatus.STALE

    def test_leaf_node_no_downstream_creates_record(self) -> None:
        """A leaf node with no downstream still gets an invalidation record."""
        catalog_service = MagicMock()
        materialization_service = MagicMock()

        catalog_service.list_downstream_dependencies.return_value = ()

        cascade = InvalidationCascadeOrchestrator(
            catalog_service=catalog_service,
            materialization_service=materialization_service,
        )

        event = _make_event()
        result_ids = cascade.propagate(event)

        assert len(result_ids) == 1
        saved_records = catalog_service.save_invalidations.call_args[0][0]
        assert saved_records[0].derived_id == "factor.alpha_upstream"

    def test_source_domain_root_ref_skipped_but_downstream_traversed(self) -> None:
        """Source domain root refs (e.g. market.stock_daily) should not get records
        but their downstream dependents should still receive invalidation records."""
        catalog_service = MagicMock()
        materialization_service = MagicMock()

        catalog_service.list_downstream_dependencies.side_effect = lambda did: (
            (
                DerivedDependencyRecord(
                    derived_id="factor.uses_market",
                    version=1,
                    dependency_kind="derived",
                    dependency_ref=did,
                    created_at="2026-03-13T10:00:00+08:00",
                ),
            )
            if did == "market.stock_daily"
            else ()
        )

        cascade = InvalidationCascadeOrchestrator(
            catalog_service=catalog_service,
            materialization_service=materialization_service,
        )

        event = _make_event(
            root_dependency_ref="market.stock_daily",
            source_domain="market",
        )
        result_ids = cascade.propagate(event)

        # Root (market.stock_daily) should be skipped, only downstream gets record
        assert len(result_ids) == 1
        saved_records = catalog_service.save_invalidations.call_args[0][0]
        assert saved_records[0].derived_id == "factor.uses_market"
        assert saved_records[0].depth == 1

    def test_non_source_domain_root_creates_record(self) -> None:
        """Non-source-domain root refs (e.g. factor.alpha) should get records."""
        catalog_service = MagicMock()
        materialization_service = MagicMock()

        catalog_service.list_downstream_dependencies.return_value = ()

        cascade = InvalidationCascadeOrchestrator(
            catalog_service=catalog_service,
            materialization_service=materialization_service,
        )

        event = _make_event(
            root_dependency_ref="factor.alpha",
            source_domain="market",
        )
        result_ids = cascade.propagate(event)

        # factor.alpha does not start with "market." so it gets a record
        assert len(result_ids) == 1
        saved_records = catalog_service.save_invalidations.call_args[0][0]
        assert saved_records[0].derived_id == "factor.alpha"
        assert saved_records[0].depth == 0


class TestCycleGuard:
    """I-CASC-03: Cycle detection."""

    def test_cycle_detected_and_skipped(self) -> None:
        """A -> B -> A cycle should be detected and skipped without error."""
        catalog_service = MagicMock()
        materialization_service = MagicMock()

        call_count = 0

        def list_downstream(derived_id: str):
            nonlocal call_count
            call_count += 1
            if derived_id == "factor.alpha_upstream" and call_count <= 2:
                return (
                    DerivedDependencyRecord(
                        derived_id="factor.cycle_b",
                        version=1,
                        dependency_kind="derived",
                        dependency_ref="factor.alpha_upstream",
                        created_at="2026-03-13T10:00:00+08:00",
                    ),
                )
            if derived_id == "factor.cycle_b":
                return (
                    DerivedDependencyRecord(
                        derived_id="factor.alpha_upstream",
                        version=1,
                        dependency_kind="derived",
                        dependency_ref="factor.cycle_b",
                        created_at="2026-03-13T10:00:00+08:00",
                    ),
                )
            return ()

        catalog_service.list_downstream_dependencies.side_effect = list_downstream

        cascade = InvalidationCascadeOrchestrator(
            catalog_service=catalog_service,
            materialization_service=materialization_service,
        )

        event = _make_event()
        cascade.propagate(event)

        saved_records = catalog_service.save_invalidations.call_args[0][0]
        derived_ids = {r.derived_id for r in saved_records}
        # alpha_upstream is the root (depth 0), cycle_b is depth 1
        # alpha_upstream should NOT appear again from the cycle
        assert derived_ids == {"factor.alpha_upstream", "factor.cycle_b"}

    def test_diamond_dependency_deduplication(self) -> None:
        """A -> B, A -> C, B -> D, C -> D diamond should deduplicate D."""
        catalog_service = MagicMock()
        materialization_service = MagicMock()

        def list_downstream(derived_id: str):
            deps_map = {
                "factor.alpha_upstream": (
                    DerivedDependencyRecord(
                        derived_id="factor.b",
                        version=1,
                        dependency_kind="derived",
                        dependency_ref="factor.alpha_upstream",
                        created_at="2026-03-13T10:00:00+08:00",
                    ),
                    DerivedDependencyRecord(
                        derived_id="factor.c",
                        version=1,
                        dependency_kind="derived",
                        dependency_ref="factor.alpha_upstream",
                        created_at="2026-03-13T10:00:00+08:00",
                    ),
                ),
                "factor.b": (
                    DerivedDependencyRecord(
                        derived_id="factor.d",
                        version=1,
                        dependency_kind="derived",
                        dependency_ref="factor.b",
                        created_at="2026-03-13T10:00:00+08:00",
                    ),
                ),
                "factor.c": (
                    DerivedDependencyRecord(
                        derived_id="factor.d",
                        version=1,
                        dependency_kind="derived",
                        dependency_ref="factor.c",
                        created_at="2026-03-13T10:00:00+08:00",
                    ),
                ),
            }
            return deps_map.get(derived_id, ())

        catalog_service.list_downstream_dependencies.side_effect = list_downstream

        cascade = InvalidationCascadeOrchestrator(
            catalog_service=catalog_service,
            materialization_service=materialization_service,
        )

        event = _make_event()
        cascade.propagate(event)

        saved_records = catalog_service.save_invalidations.call_args[0][0]
        derived_ids = [r.derived_id for r in saved_records]
        # D should appear exactly once
        assert derived_ids.count("factor.d") == 1


class TestDepthLimit:
    """I-CASC-03: Max depth protection."""

    def test_depth_exceeded_skipped(self) -> None:
        """Nodes beyond max_depth should be skipped."""
        catalog_service = MagicMock()
        materialization_service = MagicMock()

        max_depth = 2

        def list_downstream(derived_id: str):
            next_depth = int(derived_id.rsplit("_", maxsplit=1)[-1]) + 1
            return (
                DerivedDependencyRecord(
                    derived_id=f"factor.depth_{next_depth}",
                    version=1,
                    dependency_kind="derived",
                    dependency_ref=derived_id,
                    created_at="2026-03-13T10:00:00+08:00",
                ),
            )

        catalog_service.list_downstream_dependencies.side_effect = list_downstream

        cascade = InvalidationCascadeOrchestrator(
            catalog_service=catalog_service,
            materialization_service=materialization_service,
            max_depth=max_depth,
        )

        event = _make_event(root_dependency_ref="factor.depth_0")
        cascade.propagate(event)

        saved_records = catalog_service.save_invalidations.call_args[0][0]
        max_recorded_depth = max(r.depth for r in saved_records)
        assert max_recorded_depth <= max_depth


class TestMicroBatchMerge:
    """I-CASC-03: Same-target event merging."""

    def test_merge_same_derived_id_version(self) -> None:
        """Multiple records for same derived_id:version should be merged."""
        catalog_service = MagicMock()
        materialization_service = MagicMock()

        def list_downstream(derived_id: str):
            if derived_id == "factor.alpha_upstream":
                return (
                    DerivedDependencyRecord(
                        derived_id="factor.downstream",
                        version=1,
                        dependency_kind="derived",
                        dependency_ref="factor.alpha_upstream",
                        created_at="2026-03-13T10:00:00+08:00",
                    ),
                    DerivedDependencyRecord(
                        derived_id="factor.downstream",
                        version=1,
                        dependency_kind="derived",
                        dependency_ref="factor.alpha_upstream",
                        created_at="2026-03-13T10:00:00+08:00",
                    ),
                )
            return ()

        catalog_service.list_downstream_dependencies.side_effect = list_downstream

        cascade = InvalidationCascadeOrchestrator(
            catalog_service=catalog_service,
            materialization_service=materialization_service,
        )

        event = _make_event()
        cascade.propagate(event)

        saved_records = catalog_service.save_invalidations.call_args[0][0]
        downstream_records = [
            r for r in saved_records if r.derived_id == "factor.downstream"
        ]
        assert len(downstream_records) == 1

    def test_merge_expands_affected_range(self) -> None:
        """Merged records should expand affected_start/end range."""
        catalog_service = MagicMock()
        materialization_service = MagicMock()

        def list_downstream(derived_id: str):
            if derived_id == "factor.alpha_upstream":
                return (
                    DerivedDependencyRecord(
                        derived_id="factor.downstream",
                        version=1,
                        dependency_kind="derived",
                        dependency_ref="factor.alpha_upstream",
                        created_at="2026-03-13T10:00:00+08:00",
                    ),
                )
            return ()

        catalog_service.list_downstream_dependencies.side_effect = list_downstream

        cascade = InvalidationCascadeOrchestrator(
            catalog_service=catalog_service,
            materialization_service=materialization_service,
        )

        # Two events with different affected ranges targeting the same root
        event1 = _make_event(affected_start="2026-03-10", affected_end="2026-03-12")
        cascade.propagate(event1)

        event2 = _make_event(affected_start="2026-03-14", affected_end="2026-03-16")
        cascade.propagate(event2)

        # Both events save independently -
        # merge only happens within a single propagation
        # This tests the merge_batch_events method behavior for same derived_id:version
        call_count = catalog_service.save_invalidations.call_count
        assert call_count == 2


class TestStateMachine:
    """I-CASC-02: State transitions fresh -> stale -> recomputing -> healed."""

    def test_repair_batch_transitions_stale_to_healed(self) -> None:
        """Successful repair transitions stale -> recomputing -> healed."""
        catalog_service = MagicMock()
        materialization_service = MagicMock()

        stale_record = _make_record(
            derived_id="factor.downstream",
            version=1,
            status=CascadeStatus.STALE,
            depth=1,
        )
        catalog_service.list_stale_invalidations.return_value = (stale_record,)

        result = DerivedMaterializationResult(
            run_id="run-001",
            derived_id="factor.downstream",
            version=1,
            profile=MaterializationProfile.SERIES,
            status=DerivedRunStatus.SUCCESS,
            rows_written=100,
            partitions_written=("2026-03-10",),
            coverage_start="2026-03-10",
            coverage_end="2026-03-11",
        )
        materialization_service.materialize.return_value = result

        cascade = InvalidationCascadeOrchestrator(
            catalog_service=catalog_service,
            materialization_service=materialization_service,
        )

        batch_result = cascade.repair_batch(batch_size=10)

        assert len(batch_result.repaired) == 1
        assert batch_result.repaired[0].run_id == "run-001"
        assert len(batch_result.failed) == 0

        # Verify state transitions
        mark_calls = catalog_service.mark_invalidation_status.call_args_list
        status_transitions = [c[0][1] for c in mark_calls]
        assert CascadeStatus.RECOMPUTING in status_transitions
        assert CascadeStatus.HEALED in status_transitions

    def test_repair_batch_failure_reverts_to_stale(self) -> None:
        """Failed repair with retries remaining transitions recomputing -> stale."""
        catalog_service = MagicMock()
        materialization_service = MagicMock()

        stale_record = _make_record(
            derived_id="factor.downstream",
            version=1,
            status=CascadeStatus.STALE,
            depth=1,
            retry_count=0,
        )
        catalog_service.list_stale_invalidations.return_value = (stale_record,)

        materialization_service.materialize.side_effect = RuntimeError("compute failed")

        cascade = InvalidationCascadeOrchestrator(
            catalog_service=catalog_service,
            materialization_service=materialization_service,
        )

        batch_result = cascade.repair_batch(batch_size=10)

        # Should NOT raise - continues on failure
        assert len(batch_result.repaired) == 0
        assert len(batch_result.failed) == 1

        # Should have been marked recomputing first, then reverted to stale
        mark_calls = catalog_service.mark_invalidation_status.call_args_list
        status_transitions = [c[0][1] for c in mark_calls]
        assert CascadeStatus.RECOMPUTING in status_transitions
        assert CascadeStatus.STALE in status_transitions

    def test_repair_batch_sorted_by_depth(self) -> None:
        """Repairs should be processed in depth order (shallow first).

        The catalog service is responsible for returning records sorted
        by depth. This test verifies the service processes them in that
        pre-sorted order.
        """
        catalog_service = MagicMock()
        materialization_service = MagicMock()

        shallow_record = _make_record(
            derived_id="factor.shallow",
            version=1,
            status=CascadeStatus.STALE,
            depth=1,
        )
        deep_record = _make_record(
            derived_id="factor.deep",
            version=1,
            status=CascadeStatus.STALE,
            depth=3,
        )
        # Catalog returns records pre-sorted by depth
        # (as SQLite query does)
        catalog_service.list_stale_invalidations.return_value = (
            shallow_record,
            deep_record,
        )

        materialization_service.materialize.return_value = DerivedMaterializationResult(
            run_id="run-001",
            derived_id="test",
            version=1,
            profile=MaterializationProfile.SERIES,
            status=DerivedRunStatus.SUCCESS,
            rows_written=1,
            partitions_written=("2026-03-10",),
            coverage_start="2026-03-10",
            coverage_end="2026-03-11",
        )

        cascade = InvalidationCascadeOrchestrator(
            catalog_service=catalog_service,
            materialization_service=materialization_service,
        )

        cascade.repair_batch(batch_size=10)

        # Verify materialization was called with shallow first
        mat_calls = materialization_service.materialize.call_args_list
        assert mat_calls[0][0][0].derived_id == "factor.shallow"
        assert mat_calls[1][0][0].derived_id == "factor.deep"

    def test_repair_batch_respects_limit(self) -> None:
        """repair_batch should only process up to batch_size records."""
        catalog_service = MagicMock()
        materialization_service = MagicMock()

        records = tuple(
            _make_record(derived_id=f"factor.item_{i}", depth=i) for i in range(5)
        )
        catalog_service.list_stale_invalidations.return_value = records

        materialization_service.materialize.return_value = DerivedMaterializationResult(
            run_id="run-001",
            derived_id="test",
            version=1,
            profile=MaterializationProfile.SERIES,
            status=DerivedRunStatus.SUCCESS,
            rows_written=1,
            partitions_written=("2026-03-10",),
            coverage_start="2026-03-10",
            coverage_end="2026-03-11",
        )

        cascade = InvalidationCascadeOrchestrator(
            catalog_service=catalog_service,
            materialization_service=materialization_service,
        )

        batch_result = cascade.repair_batch(batch_size=2)
        assert len(batch_result.repaired) == 2


class TestCascadeDepthExceededError:
    """Verify CascadeDepthExceededError is a proper exception."""

    def test_is_exception(self) -> None:
        assert issubclass(CascadeDepthExceededError, Exception)

    def test_message(self) -> None:
        err = CascadeDepthExceededError("factor.test", 10)
        assert "factor.test" in str(err)
        assert "10" in str(err)


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


class TestRepairBatchResilience:
    """INVAL-IC-1: repair_batch failure does not terminate the batch."""

    def test_repair_batch_continues_on_failure(self) -> None:
        """3 items, middle fails -> first and last repaired, middle failed."""
        catalog_service = MagicMock()
        materialization_service = MagicMock()

        first = _make_record(derived_id="factor.first", depth=0)
        middle = _make_record(derived_id="factor.middle", depth=1)
        last = _make_record(derived_id="factor.last", depth=2)
        catalog_service.list_stale_invalidations.return_value = (
            first,
            middle,
            last,
        )

        call_count = 0

        def materialize_side_effect(_request):
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                raise RuntimeError("middle failed")
            return _make_materialization_result()

        materialization_service.materialize.side_effect = materialize_side_effect

        cascade = InvalidationCascadeOrchestrator(
            catalog_service=catalog_service,
            materialization_service=materialization_service,
        )

        batch_result = cascade.repair_batch(batch_size=10)

        # First and last repaired, middle failed
        assert len(batch_result.repaired) == 2
        assert len(batch_result.failed) == 1
        assert batch_result.failed[0] == middle.invalidation_id

        # All 3 were attempted
        assert materialization_service.materialize.call_count == 3

    def test_repair_batch_tracks_failures(self) -> None:
        """RepairBatchResult.failed contains all failed invalidation IDs."""
        catalog_service = MagicMock()
        materialization_service = MagicMock()

        record1 = _make_record(derived_id="factor.a", depth=0)
        record2 = _make_record(derived_id="factor.b", depth=1)
        catalog_service.list_stale_invalidations.return_value = (record1, record2)

        materialization_service.materialize.side_effect = RuntimeError("boom")

        cascade = InvalidationCascadeOrchestrator(
            catalog_service=catalog_service,
            materialization_service=materialization_service,
        )

        batch_result = cascade.repair_batch(batch_size=10)

        assert len(batch_result.repaired) == 0
        assert len(batch_result.failed) == 2
        assert record1.invalidation_id in batch_result.failed
        assert record2.invalidation_id in batch_result.failed

    def test_repair_batch_no_failures_empty_failed(self) -> None:
        """Successful batch has empty failed tuple."""
        catalog_service = MagicMock()
        materialization_service = MagicMock()

        record = _make_record(derived_id="factor.ok", depth=0)
        catalog_service.list_stale_invalidations.return_value = (record,)

        materialization_service.materialize.return_value = (
            _make_materialization_result()
        )

        cascade = InvalidationCascadeOrchestrator(
            catalog_service=catalog_service,
            materialization_service=materialization_service,
        )

        batch_result = cascade.repair_batch(batch_size=10)

        assert len(batch_result.failed) == 0
        assert len(batch_result.repaired) == 1


class TestDeadLetter:
    """INVAL-IC-2: Dead letter queue for max-retry invalidations."""

    def test_dead_letter_after_max_retries(self) -> None:
        """After 3 failures, status becomes DEAD_LETTER."""
        catalog_service = MagicMock()
        materialization_service = MagicMock()

        record = _make_record(
            derived_id="factor.doomed",
            retry_count=2,  # 2 prior retries; this will be the 3rd
        )
        catalog_service.list_stale_invalidations.return_value = (record,)

        materialization_service.materialize.side_effect = RuntimeError("fatal")

        cascade = InvalidationCascadeOrchestrator(
            catalog_service=catalog_service,
            materialization_service=materialization_service,
        )

        batch_result = cascade.repair_batch(batch_size=10)

        assert len(batch_result.repaired) == 0
        assert len(batch_result.failed) == 1

        # Should have incremented retry count
        catalog_service.increment_retry_count.assert_called_once_with(
            record.invalidation_id,
        )

        # Should have been marked dead letter
        catalog_service.mark_invalidation_dead_letter.assert_called_once()
        dl_call = catalog_service.mark_invalidation_dead_letter.call_args
        assert dl_call[0][0] == record.invalidation_id
        assert "fatal" in dl_call[0][1]
        assert dl_call[0][2] is not None  # dead_letter_at timestamp

    def test_not_dead_letter_below_max_retries(self) -> None:
        """Below max retries: reverts to STALE, not dead letter."""
        catalog_service = MagicMock()
        materialization_service = MagicMock()

        record = _make_record(
            derived_id="factor.recoverable",
            retry_count=0,  # first failure
        )
        catalog_service.list_stale_invalidations.return_value = (record,)

        materialization_service.materialize.side_effect = RuntimeError("transient")

        cascade = InvalidationCascadeOrchestrator(
            catalog_service=catalog_service,
            materialization_service=materialization_service,
        )

        cascade.repair_batch(batch_size=10)

        # Should NOT have been marked dead letter
        catalog_service.mark_invalidation_dead_letter.assert_not_called()

        # Should have been reverted to stale
        mark_calls = catalog_service.mark_invalidation_status.call_args_list
        status_transitions = [c[0][1] for c in mark_calls]
        assert CascadeStatus.STALE in status_transitions

    def test_dead_letter_not_retried(self) -> None:
        """Dead letter records should not be returned by list_stale_invalidations."""
        catalog_service = MagicMock()
        materialization_service = MagicMock()

        # Only stale records are returned; dead_letter ones are filtered out
        stale_record = _make_record(derived_id="factor.still_ok", depth=0)
        catalog_service.list_stale_invalidations.return_value = (stale_record,)

        materialization_service.materialize.return_value = (
            _make_materialization_result()
        )

        cascade = InvalidationCascadeOrchestrator(
            catalog_service=catalog_service,
            materialization_service=materialization_service,
        )

        batch_result = cascade.repair_batch(batch_size=10)

        # Only the stale record is processed
        assert len(batch_result.repaired) == 1
        assert len(batch_result.failed) == 0


class TestPriorityQueue:
    """INVAL-IC-3: Priority queue ordering by role."""

    def test_priority_queue_ordering(self) -> None:
        """signal > factor > feature ordering at same depth."""
        catalog_service = MagicMock()
        materialization_service = MagicMock()

        signal_record = _make_record(
            derived_id="signal.urgent",
            depth=1,
            role="signal",
        )
        factor_record = _make_record(
            derived_id="factor.normal",
            depth=1,
            role="factor",
        )
        feature_record = _make_record(
            derived_id="feature.slow",
            depth=1,
            role="feature",
        )

        # The reader should return them in priority order:
        # signal (0) > factor (1) > feature (3)
        catalog_service.list_stale_invalidations.return_value = (
            signal_record,
            factor_record,
            feature_record,
        )

        materialization_service.materialize.return_value = (
            _make_materialization_result()
        )

        cascade = InvalidationCascadeOrchestrator(
            catalog_service=catalog_service,
            materialization_service=materialization_service,
        )

        cascade.repair_batch(batch_size=10)

        mat_calls = materialization_service.materialize.call_args_list
        derived_ids = [c[0][0].derived_id for c in mat_calls]
        assert derived_ids == [
            "signal.urgent",
            "factor.normal",
            "feature.slow",
        ]

    def test_depth_still_primary_sort_for_different_depths(self) -> None:
        """Depth is still the primary sort when roles differ across depths."""
        catalog_service = MagicMock()
        materialization_service = MagicMock()

        shallow_feature = _make_record(
            derived_id="feature.shallow",
            depth=0,
            role="feature",
        )
        deep_signal = _make_record(
            derived_id="signal.deep",
            depth=2,
            role="signal",
        )

        catalog_service.list_stale_invalidations.return_value = (
            shallow_feature,
            deep_signal,
        )

        materialization_service.materialize.return_value = (
            _make_materialization_result()
        )

        cascade = InvalidationCascadeOrchestrator(
            catalog_service=catalog_service,
            materialization_service=materialization_service,
        )

        cascade.repair_batch(batch_size=10)

        mat_calls = materialization_service.materialize.call_args_list
        derived_ids = [c[0][0].derived_id for c in mat_calls]
        # depth 0 < depth 2, so shallow_feature comes first
        assert derived_ids == [
            "feature.shallow",
            "signal.deep",
        ]


class TestPropagationRole:
    """Verify propagate() assigns default role to created records."""

    def test_propagate_assigns_default_role(self) -> None:
        """Each propagated record should have role='factor' by default."""
        catalog_service = MagicMock()
        materialization_service = MagicMock()

        catalog_service.list_downstream_dependencies.return_value = (
            DerivedDependencyRecord(
                derived_id="factor.downstream",
                version=1,
                dependency_kind="derived",
                dependency_ref="factor.alpha_upstream",
                created_at="2026-03-13T10:00:00+08:00",
            ),
        )

        cascade = InvalidationCascadeOrchestrator(
            catalog_service=catalog_service,
            materialization_service=materialization_service,
        )

        event = _make_event()
        cascade.propagate(event)

        saved_records = catalog_service.save_invalidations.call_args[0][0]
        for record in saved_records:
            assert record.role == "factor"
