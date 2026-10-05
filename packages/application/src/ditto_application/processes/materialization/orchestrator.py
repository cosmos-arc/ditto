"""
App-side unified derived materialization orchestration.

Provides ``DerivedMaterializationOrchestrator`` for compile-execute-persist
lifecycle.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from dataclasses import asdict, dataclass, replace
from datetime import datetime
from typing import NamedTuple, Protocol, runtime_checkable
from uuid import uuid4

import polars as pl
from ditto_data.catalog.contracts import DataAssetRef
from ditto_data.lineage.contracts import (
    DataLineageRecorder,
    LineageEvent,
    LineageInputRef,
    LineageOutputRef,
)
from ditto_features.compile_cache import SQLiteCompileCache
from ditto_features.derived_types import DerivedSpec, MaterializationProfile
from ditto_features.expression import CompiledDerivedExpression
from ditto_features.materialization import (
    DerivedExecutionPlan,
    DerivedExecutionPlanner,
    DerivedMaterializationRequest,
    DerivedMaterializationResult,
    DerivedRunMode,
    DerivedRunStatus,
    DerivedRunTrigger,
)
from ditto_features.materialization.publication import CompatibilityManifestRecord
from ditto_features.models.derived import (
    DerivedCheckpointRecord,
    DerivedCheckpointStatus,
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
    DerivedArtifactReader,
    DerivedCatalogService,
    extract_partition_keys,
)

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
from ditto_application.processes.materialization.source_snapshot_resolver import (
    SourceSnapshotProvenance,
    SourceSnapshotResolver,
)
from ditto_application.processes.materialization.types import (
    DerivedInputProvider,
    InputContext,
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


@dataclass(frozen=True)
class MaterializationRuntimePorts:
    """Runtime collaborators required by the derived materialization orchestrator."""

    catalog_service: DerivedCatalogService
    compile_cache_service: SQLiteCompileCache
    artifact_writer: ArtifactPersistenceService
    input_provider: DerivedInputProvider
    source_snapshot_resolver: SourceSnapshotResolver | None = None
    universe_provider: UniverseProvider | None = None
    artifact_reader: DerivedArtifactReader | None = None
    lineage_recorder: DataLineageRecorder | None = None


@dataclass(frozen=True)
class MaterializationRunRecordContext:
    """Fields required to assemble one derived materialization run record."""

    run_id: str
    spec: DerivedSpec
    request: DerivedMaterializationRequest
    plan: DerivedExecutionPlan
    status: DerivedRunStatus
    created_at: str
    started_at: str
    rows_written: int = 0
    partitions_written: tuple[str, ...] = ()
    error_message: str | None = None
    finished_at: str | None = None


@dataclass(frozen=True)
class MaterializedDataPersistenceContext:
    """Fields required to persist one materialized derived output."""

    spec: DerivedSpec
    spec_record: DerivedSpecRecord
    request: DerivedMaterializationRequest
    plan: DerivedExecutionPlan
    compiled: CompiledDerivedExpression
    run: _RunIdentity
    materialized_frame: pl.DataFrame
    source_snapshot_ids: tuple[str, ...]


def _make_run_record(
    ctx: MaterializationRunRecordContext,
) -> DerivedRunRecord:
    """构造 DerivedRunRecord，统一共享字段映射。"""
    return DerivedRunRecord(
        run_id=ctx.run_id,
        derived_id=ctx.spec.id,
        version=ctx.spec.version,
        mode=ctx.request.mode.value,
        trigger=ctx.request.trigger.value,
        request_start=ctx.request.request_start,
        request_end=ctx.request.request_end,
        compute_start=ctx.plan.compute_start,
        compute_end=ctx.plan.compute_end,
        source_snapshot_id=ctx.request.source_snapshot_id,
        status=ctx.status.value,
        rows_written=ctx.rows_written,
        partitions_written=ctx.partitions_written,
        error_message=ctx.error_message,
        created_at=ctx.created_at,
        started_at=ctx.started_at,
        finished_at=ctx.finished_at,
    )


def _derived_output_asset(spec: DerivedSpec) -> DataAssetRef:
    return DataAssetRef(
        dataset_id=spec.id,
        namespace="derived",
        partition_keys=(f"version={spec.version}",),
    )


def _dependency_asset(kind: str, ref: str) -> DataAssetRef:
    if kind == "derived":
        return DataAssetRef(dataset_id=ref, namespace="derived")
    if "." in ref:
        namespace, dataset_id = ref.split(".", maxsplit=1)
        return DataAssetRef(dataset_id=dataset_id, namespace=namespace)
    return DataAssetRef(dataset_id=ref, namespace=kind)


def _lineage_inputs(dependencies: tuple[str, ...]) -> tuple[LineageInputRef, ...]:
    return tuple(
        LineageInputRef(asset=_dependency_asset(kind, ref), role=kind)
        for kind, ref in dependency_refs(dependencies)
    )


def _request_with_source_snapshot(
    request: DerivedMaterializationRequest,
    source_snapshot_id: str | None,
) -> DerivedMaterializationRequest:
    if request.source_snapshot_id == source_snapshot_id:
        return request
    return replace(request, source_snapshot_id=source_snapshot_id)


def _checkpoint_records(
    *,
    derived_id: str,
    version: int,
    run: _RunIdentity,
    partitions: tuple[PartitionInfo, ...],
    status: DerivedCheckpointStatus,
) -> tuple[DerivedCheckpointRecord, ...]:
    """Build post-write lifecycle stage rows (rows/checksum 来自写后事实)."""
    return _checkpoint_rows(
        derived_id=derived_id,
        version=version,
        run=run,
        status=status,
        facts=(
            (partition.partition_key, partition.row_count, partition.checksum)
            for partition in partitions
        ),
    )


def _planned_checkpoint_records(
    *,
    derived_id: str,
    version: int,
    run: _RunIdentity,
    partition_keys: tuple[str, ...],
) -> tuple[DerivedCheckpointRecord, ...]:
    """Build PLANNED intent rows（写入前，尚无行数与 checksum 事实）."""
    return _checkpoint_rows(
        derived_id=derived_id,
        version=version,
        run=run,
        status=DerivedCheckpointStatus.PLANNED,
        facts=((key, 0, None) for key in partition_keys),
    )


def _checkpoint_rows(
    *,
    derived_id: str,
    version: int,
    run: _RunIdentity,
    status: DerivedCheckpointStatus,
    facts: Iterator[tuple[str, int, str | None]],
) -> tuple[DerivedCheckpointRecord, ...]:
    completed_at = now_iso() if status is DerivedCheckpointStatus.COMPLETE else None
    return tuple(
        DerivedCheckpointRecord(
            derived_id=derived_id,
            version=version,
            partition_key=partition_key,
            status=status.value,
            rows_written=row_count,
            checksum=checksum,
            error_message=None,
            started_at=run.started_at,
            completed_at=completed_at,
        )
        for partition_key, row_count, checksum in facts
    )


# ===========================================================================
# DerivedMaterializationOrchestrator
# ===========================================================================


class DerivedMaterializationOrchestrator:
    """Compile, execute, and persist one unified derived run."""

    def __init__(self, ports: MaterializationRuntimePorts) -> None:
        self._catalog_service = ports.catalog_service
        self._compile_cache_service = ports.compile_cache_service
        self._artifact_writer = ports.artifact_writer
        self._input_provider = ports.input_provider
        self._source_snapshot_resolver = ports.source_snapshot_resolver
        self._universe_provider = ports.universe_provider
        self._artifact_reader = ports.artifact_reader
        self._lineage_recorder = ports.lineage_recorder
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
        plan = self._planner.plan(
            spec=spec,
            compiled=compiled,
            request=request,
        )
        run_id = f"drv-{uuid4().hex[:12]}"
        started_at = now_iso()
        self._catalog_service.save_run(
            _make_run_record(
                MaterializationRunRecordContext(
                    run_id=run_id,
                    spec=spec,
                    request=request,
                    plan=plan,
                    status=DerivedRunStatus.RUNNING,
                    created_at=started_at,
                    started_at=started_at,
                )
            )
        )
        effective_request = request
        try:
            input_context = InputContext(
                spec=spec,
                request=request,
                plan=plan,
                dependencies=compiled.analysis.dependencies,
            )
            source_snapshot_provenance = self._resolve_source_snapshot_provenance(
                input_context
            )
            effective_request = _request_with_source_snapshot(
                request,
                source_snapshot_provenance.source_snapshot_id,
            )
            input_frame = self._input_provider.load_input(input_context)
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
                MaterializedDataPersistenceContext(
                    spec=spec,
                    spec_record=spec_record,
                    request=effective_request,
                    plan=plan,
                    compiled=compiled,
                    run=_RunIdentity(run_id, started_at),
                    materialized_frame=materialized_frame,
                    source_snapshot_ids=source_snapshot_provenance.source_snapshot_ids,
                )
            )
        except Exception as exc:
            finished_at = now_iso()
            self._catalog_service.save_run(
                _make_run_record(
                    MaterializationRunRecordContext(
                        run_id=run_id,
                        spec=spec,
                        request=effective_request,
                        plan=plan,
                        status=DerivedRunStatus.FAILED,
                        error_message=str(exc),
                        created_at=started_at,
                        started_at=started_at,
                        finished_at=finished_at,
                    )
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
        ctx: MaterializedDataPersistenceContext,
    ) -> DerivedMaterializationResult:
        """
        Persist materialized data according to the spec's profile.

        Handles both DERIVE (ephemeral) and DURABLE (partitioned) paths.
        """
        spec = ctx.spec
        request = ctx.request
        plan = ctx.plan
        run = ctx.run
        materialized_frame = ctx.materialized_frame
        time_key = spec.effective_time_keys[0]
        window = pl.col(time_key).cast(pl.String).str.slice(0, 10)
        materialized_frame = materialized_frame.filter(
            window.is_between(
                pl.lit(request.request_start), pl.lit(request.request_end)
            )
        )
        if spec.materialization_profile == MaterializationProfile.DERIVE:
            self._artifact_writer.write_ephemeral_result(
                spec=ctx.spec_record,
                run_id=run.run_id,
                frame=materialized_frame,
            )
            return self._finalize_derive_run(
                spec=spec,
                request=request,
                plan=plan,
                run=run,
                rows_written=materialized_frame.height,
                dependencies=ctx.compiled.analysis.dependencies,
            )
        manifest_record = build_manifest_record(
            spec=spec,
            version=spec.version,
            compile_identity=ctx.compiled.compile_identity,
            source_snapshot_id=request.source_snapshot_id,
            source_snapshot_ids=ctx.source_snapshot_ids,
            knowledge_cutoff=request.request_end,
        )
        minimal_dq_record = build_minimal_dq_record(
            spec=spec,
            run_id=run.run_id,
            version=spec.version,
            frame=materialized_frame,
        )
        if not minimal_dq_record.passed:
            raise AppProcessError(
                "minimal DQ failed, refusing to publish: "
                + f"derived_id={spec.id} v={spec.version} "
                + f"failed_checks={minimal_dq_record.payload.get('failed_checks')}"
            )
        self._verify_deterministic_retry(
            spec=spec,
            request=request,
            manifest_record=manifest_record,
            frame=materialized_frame,
        )
        time_key = spec.effective_time_keys[0]
        # 三阶段 checkpoint（#418，复用 #393 语义）：写入前落 PLANNED 意图；
        # 部分失败时目录停留可发现的恢复态，读取侧拒绝非 COMPLETE 分区。
        self._catalog_service.save_checkpoints(
            _planned_checkpoint_records(
                derived_id=spec.id,
                version=spec.version,
                run=run,
                partition_keys=extract_partition_keys(materialized_frame, time_key),
            )
        )
        partitions = self._artifact_writer.write_durable_partitions(
            spec=ctx.spec_record,
            time_key=time_key,
            run_id=run.run_id,
            frame=materialized_frame,
            request_start=request.request_start,
            request_end=request.request_end,
            source_snapshot_id=request.source_snapshot_id,
        )
        # 分区文件已原子落盘：簿记分区行并推进 PAYLOAD_COMMITTED（可恢复态）。
        self._catalog_service.save_partitions(
            tuple(
                DerivedPartitionRecord(
                    run_id=run.run_id,
                    derived_id=spec.id,
                    version=spec.version,
                    partition_key=partition.partition_key,
                    partition_path=partition.partition_path,
                    row_count=partition.row_count,
                    checksum=partition.checksum,
                    written_at=now_iso(),
                )
                for partition in partitions
            )
        )
        self._catalog_service.save_checkpoints(
            _checkpoint_records(
                derived_id=spec.id,
                version=spec.version,
                run=run,
                partitions=partitions,
                status=DerivedCheckpointStatus.PAYLOAD_COMMITTED,
            )
        )
        self._artifact_writer.write_artifact_metadata(
            ArtifactMetadataParams(
                spec=ctx.spec_record,
                run_id=run.run_id,
                compile_identity=asdict(ctx.compiled.compile_identity),
                analysis=asdict(ctx.compiled.analysis),
                partitions=partitions,
                request_start=request.request_start,
                request_end=request.request_end,
                source_snapshot_id=request.source_snapshot_id,
                source_snapshot_ids=ctx.source_snapshot_ids,
                manifest_record=manifest_record,
                minimal_dq_record=minimal_dq_record,
            ),
        )
        return self._finalize_durable_run(
            spec=spec,
            request=request,
            plan=plan,
            run=run,
            frame=materialized_frame,
            partitions=partitions,
            dependencies=ctx.compiled.analysis.dependencies,
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
        self._record_materialization_lineage(
            spec=spec,
            run_id=run.run_id,
            finished_at=finished_at,
            dependencies=dependencies,
        )
        self._catalog_service.save_run(
            _make_run_record(
                MaterializationRunRecordContext(
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
        self._catalog_service.save_checkpoints(
            _checkpoint_records(
                derived_id=spec.id,
                version=spec.version,
                run=run,
                partitions=partitions,
                status=DerivedCheckpointStatus.COMPLETE,
            )
        )
        previous_state = self._catalog_service.get_state(spec.id)
        starts = [request.request_start]
        ends = [request.request_end]
        if previous_state is not None and previous_state.active_version == spec.version:
            if previous_state.coverage_start:
                starts.append(previous_state.coverage_start)
            if previous_state.coverage_end:
                ends.append(previous_state.coverage_end)
        self._catalog_service.save_state(
            DerivedStateRecord(
                derived_id=spec.id,
                active_version=spec.version,
                coverage_start=min(starts),
                coverage_end=max(ends),
                watermark=max(ends),
                latest_run_id=run.run_id,
                latest_run_status=DerivedRunStatus.SUCCESS.value,
                total_rows=sum(
                    item.rows_written or 0
                    for item in self._catalog_service.list_checkpoints(
                        spec.id, spec.version
                    )
                ),
                updated_at=finished_at,
            )
        )
        self._persist_dependencies(
            derived_id=spec.id,
            version=spec.version,
            dependencies=dependencies,
            created_at=finished_at,
        )
        self._catalog_service.publish_version(
            derived_id=spec.id,
            version=spec.version,
            updated_at=finished_at,
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
        self._record_materialization_lineage(
            spec=spec,
            run_id=run.run_id,
            finished_at=finished_at,
            dependencies=dependencies,
        )
        self._catalog_service.save_run(
            _make_run_record(
                MaterializationRunRecordContext(
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

    def _record_materialization_lineage(
        self,
        *,
        spec: DerivedSpec,
        run_id: str,
        finished_at: str,
        dependencies: tuple[str, ...],
    ) -> None:
        recorder = self._lineage_recorder
        if recorder is None:
            return
        recorder.record_event(
            LineageEvent(
                run_id=run_id,
                operation="materialize",
                inputs=_lineage_inputs(dependencies),
                outputs=(
                    LineageOutputRef(
                        asset=_derived_output_asset(spec),
                        role="derived",
                    ),
                ),
                timestamp=datetime.fromisoformat(finished_at),
            )
        )

    def _resolve_source_snapshot_provenance(
        self,
        context: InputContext,
    ) -> SourceSnapshotProvenance:
        resolver = self._source_snapshot_resolver
        if resolver is None:
            return SourceSnapshotProvenance.from_ids(
                (context.request.source_snapshot_id,)
            )
        provenance = resolver.resolve(context)
        if provenance.source_snapshot_id is not None or provenance.source_snapshot_ids:
            return provenance
        return SourceSnapshotProvenance.from_ids((context.request.source_snapshot_id,))

    def _verify_deterministic_retry(
        self,
        *,
        spec: DerivedSpec,
        request: DerivedMaterializationRequest,
        manifest_record: CompatibilityManifestRecord,
        frame: pl.DataFrame,
    ) -> None:
        """
        相同输入身份的重试必须产出一致内容（#444 直线发布判定）.

        遍历成功 run 的完整窗口与 manifest 身份，读取其不可变分区副本。
        比对发生在任何写入之前，不能拿当前分区冒充旧身份。
        """
        reader = self._artifact_reader
        if reader is None:
            return
        sort_keys = [*spec.entity_keys, *spec.effective_time_keys]
        expected = frame.sort(sort_keys)
        for previous in self._catalog_service.list_successful_runs(
            spec.id, spec.version
        ):
            if (previous.request_start, previous.request_end) != (
                request.request_start,
                request.request_end,
            ):
                continue
            if (
                reader.read_run_manifest_hash(spec.id, spec.version, previous.run_id)
                != manifest_record.manifest_hash
            ):
                continue
            published = reader.read_run_frame(spec.id, spec.version, previous.run_id)
            if expected.is_empty() and published.is_empty():
                continue
            time_key = (
                pl.col(spec.effective_time_keys[0]).cast(pl.String).str.slice(0, 10)
            )
            actual = published.filter(
                time_key.is_between(
                    pl.lit(request.request_start), pl.lit(request.request_end)
                )
            )
            if not expected.equals(actual.select(frame.columns).sort(sort_keys)):
                raise AppProcessError(
                    "deterministic retry mismatch: same input identity produced "
                    + f"different content for derived_id={spec.id} v={spec.version}; "
                    + "published artifacts were not modified"
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
