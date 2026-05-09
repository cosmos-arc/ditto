"""
App-side unified derived materialization orchestration.

Provides ``DerivedMaterializationOrchestrator`` for compile-execute-persist
lifecycle.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import asdict
from typing import NamedTuple, Protocol, runtime_checkable
from uuid import uuid4

import polars as pl
from ditto_features.compile_cache import SQLiteCompileCache
from ditto_features.expression import CompiledDerivedExpression, CompileIdentity
from ditto_features.materialization import (
    DerivedExecutionPlan,
    DerivedExecutionPlanner,
    DerivedMaterializationRequest,
    DerivedMaterializationResult,
    DerivedRunMode,
    DerivedRunStatus,
    DerivedRunTrigger,
)
from ditto_features.models.derived import (
    DerivedCheckpointRecord,
    DerivedDependencyRecord,
    DerivedPartitionRecord,
    DerivedRunRecord,
    DerivedSpecRecord,
    DerivedStateRecord,
    PartitionInfo,
)
from ditto_features.services import (
    ArtifactMetadataParams,
    ArtifactPersistenceService,
    DerivedCatalogService,
    PublicationSafetyRecordService,
)
from ditto_kernel.publication_safety import DerivedMinimalDQSummaryRecord
from ditto_kernel.strategy import DerivedSpec, MaterializationProfile

from ditto_application.config import now_iso
from ditto_application.exceptions import AppProcessError
from ditto_application.processes.materialization.dependencies import (
    apply_cs_amplification,
)
from ditto_application.processes.materialization.dependency_refs import dependency_refs
from ditto_application.processes.materialization.factor_orthogonalization import (
    FactorOrthogonalizationService,
)
from ditto_application.processes.materialization.manifest_builder import (
    build_manifest_record,
)
from ditto_application.processes.materialization.minimal_dq import (
    build_minimal_dq_record,
)
from ditto_application.processes.materialization.runtime_input_provider import (
    RuntimeDerivedInputProvider,
)
from ditto_application.processes.materialization.types import (
    DerivedInputProvider,
    InputContext,
    earliest_pending_start,
    hydrate_spec,
    prepare_input_frame,
)

__all__ = [
    "DerivedMaterializationOrchestrator",
    "FactorOrthogonalizationService",
    "RuntimeDerivedInputProvider",
    "UniverseProvider",
    "apply_cs_amplification",
]


# ===========================================================================
# Universe provider protocol
# ===========================================================================


@runtime_checkable
class UniverseProvider(Protocol):
    """Abstraction for resolving universe instrument membership."""

    def get_universe(self, universe_id: str, asof: str | None = None) -> list[int]:
        """Return instrument IDs belonging to *universe_id* as of *asof*."""
        ...


class _RunIdentity(NamedTuple):
    """Pairs run_id with started_at for finalize helpers."""

    run_id: str
    started_at: str


def _make_run_record(  # noqa: PLR0913
    *,
    run_id: str,
    spec: DerivedSpec,
    request: DerivedMaterializationRequest,
    plan: DerivedExecutionPlan,
    status: DerivedRunStatus,
    rows_written: int = 0,
    partitions_written: tuple[str, ...] = (),
    error_message: str | None = None,
    created_at: str,
    started_at: str,
    finished_at: str | None = None,
) -> DerivedRunRecord:
    """构造 DerivedRunRecord，统一共享字段映射。"""
    return DerivedRunRecord(
        run_id=run_id,
        derived_id=spec.id,
        version=spec.version,
        mode=request.mode.value,
        trigger=request.trigger.value,
        request_start=request.request_start,
        request_end=request.request_end,
        compute_start=plan.compute_start,
        compute_end=plan.compute_end,
        source_snapshot_id=request.source_snapshot_id,
        status=status.value,
        rows_written=rows_written,
        partitions_written=partitions_written,
        error_message=error_message,
        created_at=created_at,
        started_at=started_at,
        finished_at=finished_at,
    )


# ===========================================================================
# DerivedMaterializationOrchestrator
# ===========================================================================


class DerivedMaterializationOrchestrator:
    """Compile, execute, and persist one unified derived run."""

    def __init__(
        self,
        *,
        catalog_service: DerivedCatalogService,
        compile_cache_service: SQLiteCompileCache,
        artifact_writer: ArtifactPersistenceService,
        input_provider: DerivedInputProvider,
        universe_provider: UniverseProvider | None = None,
        publication_record_service: PublicationSafetyRecordService | None = None,
    ) -> None:
        self._catalog_service = catalog_service
        self._compile_cache_service = compile_cache_service
        self._artifact_writer = artifact_writer
        self._input_provider = input_provider
        self._universe_provider = universe_provider
        self._publication_record_service = publication_record_service
        self._planner = DerivedExecutionPlanner()

    def materialize(
        self,
        request: DerivedMaterializationRequest,
    ) -> DerivedMaterializationResult:
        """Run a single materialization request end-to-end."""
        spec_record = self._catalog_service.get_spec(
            request.derived_id,
            request.version,
        )
        if spec_record is None:
            raise AppProcessError(
                "derived spec not found for "
                + f"derived_id={request.derived_id} version={request.version}"
            )
        version_record = self._catalog_service.get_version(
            request.derived_id,
            request.version,
        )
        if version_record is None:
            raise AppProcessError(
                "derived version not found for "
                + f"derived_id={request.derived_id} version={request.version}"
            )
        spec = hydrate_spec(spec_record)
        compiled = self._compile_cache_service.get_or_compile(
            spec,
            force_recompile=request.force_recompile,
        )
        earliest_pending = earliest_pending_start(
            self._catalog_service.list_stale_invalidations(),
            spec.id,
            spec.version,
        )
        plan = self._planner.plan(
            spec=spec,
            compiled=compiled,
            request=request,
            earliest_pending_invalidation_start=earliest_pending,
        )
        run_id = f"drv-{uuid4().hex[:12]}"
        started_at = now_iso()
        self._catalog_service.save_run(
            _make_run_record(
                run_id=run_id,
                spec=spec,
                request=request,
                plan=plan,
                status=DerivedRunStatus.RUNNING,
                created_at=started_at,
                started_at=started_at,
            )
        )
        try:
            input_frame = self._input_provider.load_input(
                InputContext(
                    spec=spec,
                    request=request,
                    plan=plan,
                    dependencies=compiled.analysis.dependencies,
                )
            )
            prepared_frame = prepare_input_frame(
                frame=input_frame,
                spec=spec,
                dependencies=compiled.analysis.dependencies,
            )
            materialized_frame = prepared_frame.with_columns(
                compiled.expr.alias("value")
            )
            materialized_frame = self._maybe_apply_cs_amplification(
                frame=materialized_frame,
                spec=spec,
                plan=plan,
            )
            return self._persist_materialized_data(
                spec=spec,
                spec_record=spec_record,
                request=request,
                plan=plan,
                compiled=compiled,
                run=_RunIdentity(run_id, started_at),
                materialized_frame=materialized_frame,
            )
        except Exception as exc:
            finished_at = now_iso()
            self._catalog_service.save_run(
                _make_run_record(
                    run_id=run_id,
                    spec=spec,
                    request=request,
                    plan=plan,
                    status=DerivedRunStatus.FAILED,
                    error_message=str(exc),
                    created_at=started_at,
                    started_at=started_at,
                    finished_at=finished_at,
                )
            )
            raise

    def materialize_daily(
        self,
        *,
        trade_date: str,
        mode: str = "incremental",
        derived_ids: Sequence[str] | None = None,
    ) -> tuple[DerivedMaterializationResult, ...]:
        """Materialize durable profiles scheduled for one trade date."""
        specs = self._catalog_service.list_specs(
            derived_ids=derived_ids,
            durable_only=True,
        )
        run_mode = DerivedRunMode(mode)
        return tuple(
            self.materialize(
                DerivedMaterializationRequest(
                    derived_id=spec_record.derived_id,
                    version=spec_record.version,
                    mode=run_mode,
                    request_start=trade_date,
                    request_end=trade_date,
                    trigger=DerivedRunTrigger.SCHEDULED,
                    source_snapshot_id=None,
                )
            )
            for spec_record in specs
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _persist_materialized_data(
        self,
        *,
        spec: DerivedSpec,
        spec_record: DerivedSpecRecord,
        request: DerivedMaterializationRequest,
        plan: DerivedExecutionPlan,
        compiled: CompiledDerivedExpression,
        run: _RunIdentity,
        materialized_frame: pl.DataFrame,
    ) -> DerivedMaterializationResult:
        """
        Persist materialized data according to the spec's profile.

        Handles both DERIVE (ephemeral) and DURABLE (partitioned) paths.
        """
        if spec.materialization_profile == MaterializationProfile.DERIVE:
            self._artifact_writer.write_ephemeral_result(
                spec=spec_record,
                run_id=run.run_id,
                frame=materialized_frame,
            )
            return self._finalize_derive_run(
                spec=spec,
                request=request,
                plan=plan,
                run=run,
                rows_written=materialized_frame.height,
                dependencies=compiled.analysis.dependencies,
            )
        time_key = spec.effective_time_keys[0]
        partitions = self._artifact_writer.write_durable_partitions(
            spec=spec_record,
            time_key=time_key,
            run_id=run.run_id,
            frame=materialized_frame,
            request_start=request.request_start,
            request_end=request.request_end,
            source_snapshot_id=request.source_snapshot_id,
        )
        self._artifact_writer.write_artifact_metadata(
            ArtifactMetadataParams(
                spec=spec_record,
                run_id=run.run_id,
                compile_identity=asdict(compiled.compile_identity),
                analysis=asdict(compiled.analysis),
                partitions=partitions,
                request_start=request.request_start,
                request_end=request.request_end,
                source_snapshot_id=request.source_snapshot_id,
            ),
        )
        minimal_dq_record = None
        if self._publication_record_service is not None:
            minimal_dq_record = build_minimal_dq_record(
                spec=spec,
                run_id=run.run_id,
                version=spec.version,
                frame=materialized_frame,
            )
            self._persist_publication_safety_records(
                spec=spec,
                spec_record=spec_record,
                run_id=run.run_id,
                request=request,
                compile_identity=compiled.compile_identity,
                partitions=partitions,
                minimal_dq_record=minimal_dq_record,
            )
        return self._finalize_durable_run(
            spec=spec,
            request=request,
            plan=plan,
            run=run,
            frame=materialized_frame,
            partitions=partitions,
            dependencies=compiled.analysis.dependencies,
        )

    def _finalize_derive_run(
        self,
        *,
        spec: DerivedSpec,
        request: DerivedMaterializationRequest,
        plan: DerivedExecutionPlan,
        run: _RunIdentity,
        rows_written: int,
        dependencies: tuple[str, ...],
    ) -> DerivedMaterializationResult:
        finished_at = now_iso()
        self._persist_dependencies(
            derived_id=spec.id,
            version=spec.version,
            dependencies=dependencies,
            created_at=finished_at,
        )
        result = DerivedMaterializationResult(
            run_id=run.run_id,
            derived_id=spec.id,
            version=spec.version,
            profile=spec.materialization_profile,
            status=DerivedRunStatus.SUCCESS,
            rows_written=rows_written,
            partitions_written=(),
            coverage_start=plan.compute_start,
            coverage_end=plan.compute_end,
        )
        self._catalog_service.save_run(
            _make_run_record(
                run_id=run.run_id,
                spec=spec,
                request=request,
                plan=plan,
                status=DerivedRunStatus.SUCCESS,
                rows_written=rows_written,
                created_at=run.started_at,
                started_at=run.started_at,
                finished_at=finished_at,
            )
        )
        return result

    def _finalize_durable_run(
        self,
        *,
        spec: DerivedSpec,
        request: DerivedMaterializationRequest,
        plan: DerivedExecutionPlan,
        run: _RunIdentity,
        frame: pl.DataFrame,
        partitions: tuple[PartitionInfo, ...],
        dependencies: tuple[str, ...],
    ) -> DerivedMaterializationResult:
        finished_at = now_iso()
        partition_records = tuple(
            DerivedPartitionRecord(
                run_id=run.run_id,
                derived_id=spec.id,
                version=spec.version,
                partition_key=partition.partition_key,
                partition_path=partition.partition_path,
                row_count=partition.row_count,
                checksum=partition.checksum,
                written_at=finished_at,
            )
            for partition in partitions
        )
        checkpoint_records = tuple(
            DerivedCheckpointRecord(
                derived_id=spec.id,
                version=spec.version,
                partition_key=partition.partition_key,
                status="done",
                rows_written=partition.row_count,
                checksum=partition.checksum,
                error_message=None,
                started_at=run.started_at,
                completed_at=finished_at,
            )
            for partition in partitions
        )
        self._catalog_service.save_partitions(partition_records)
        self._catalog_service.save_checkpoints(checkpoint_records)
        self._catalog_service.save_state(
            DerivedStateRecord(
                derived_id=spec.id,
                active_version=spec.version,
                coverage_start=plan.compute_start,
                coverage_end=plan.compute_end,
                watermark=plan.compute_end,
                latest_run_id=run.run_id,
                latest_run_status=DerivedRunStatus.SUCCESS.value,
                total_rows=frame.height,
                updated_at=finished_at,
            )
        )
        self._persist_dependencies(
            derived_id=spec.id,
            version=spec.version,
            dependencies=dependencies,
            created_at=finished_at,
        )
        result = DerivedMaterializationResult(
            run_id=run.run_id,
            derived_id=spec.id,
            version=spec.version,
            profile=spec.materialization_profile,
            status=DerivedRunStatus.SUCCESS,
            rows_written=frame.height,
            partitions_written=tuple(
                partition.partition_key for partition in partitions
            ),
            coverage_start=plan.compute_start,
            coverage_end=plan.compute_end,
        )
        self._catalog_service.save_run(
            _make_run_record(
                run_id=run.run_id,
                spec=spec,
                request=request,
                plan=plan,
                status=DerivedRunStatus.SUCCESS,
                rows_written=frame.height,
                partitions_written=result.partitions_written,
                created_at=run.started_at,
                started_at=run.started_at,
                finished_at=finished_at,
            )
        )
        return result

    def _persist_dependencies(
        self,
        *,
        derived_id: str,
        version: int,
        dependencies: tuple[str, ...],
        created_at: str,
    ) -> None:
        records = tuple(
            DerivedDependencyRecord(
                derived_id=derived_id,
                version=version,
                dependency_kind=dependency_kind,
                dependency_ref=dependency_ref,
                created_at=created_at,
            )
            for dependency_kind, dependency_ref in dependency_refs(dependencies)
        )
        if records:
            self._catalog_service.save_dependencies(records)

    def _persist_publication_safety_records(
        self,
        *,
        spec: DerivedSpec,
        spec_record: DerivedSpecRecord,
        run_id: str,
        request: DerivedMaterializationRequest,
        compile_identity: CompileIdentity,
        partitions: tuple[PartitionInfo, ...],
        minimal_dq_record: DerivedMinimalDQSummaryRecord,
    ) -> None:
        publication_record_service = self._publication_record_service
        if publication_record_service is None:
            raise AppProcessError("publication record service is not configured")
        manifest_record = build_manifest_record(
            spec=spec,
            version=spec.version,
            compile_identity=compile_identity,
        )
        publication_record_service.save_manifest(manifest_record)
        publication_record_service.save_minimal_dq_summary(minimal_dq_record)
        self._artifact_writer.update_artifact_metadata(
            spec=spec_record,
            run_id=run_id,
            compile_identity=asdict(compile_identity),
            partitions=partitions,
            source_snapshot_id=request.source_snapshot_id,
            manifest_record=manifest_record,
            minimal_dq_record=minimal_dq_record,
        )

    def _maybe_apply_cs_amplification(
        self,
        *,
        frame: pl.DataFrame,
        spec: DerivedSpec,
        plan: DerivedExecutionPlan,
    ) -> pl.DataFrame:
        """Apply cross-section amplification when the plan requires full-day data."""
        if not plan.requires_full_day:
            return frame
        if spec.universe_id is None:
            return frame
        if self._universe_provider is None:
            return frame
        instrument_ids = self._universe_provider.get_universe(
            spec.universe_id,
            asof=plan.compute_start,
        )
        if not instrument_ids:
            return frame
        return apply_cs_amplification(
            frame=frame,
            instrument_ids=instrument_ids,
            time_keys=spec.effective_time_keys,
            entity_keys=spec.entity_keys,
        )
