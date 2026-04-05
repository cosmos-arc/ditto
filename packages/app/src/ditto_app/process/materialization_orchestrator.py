"""
Port-side unified derived materialization orchestration.

Provides ``DerivedMaterializationOrchestrator`` for compile-execute-persist
lifecycle, ``RuntimeDerivedInputProvider`` for production input loading,
and ``FactorOrthogonalizationService`` for factor decorrelation.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import asdict
from pathlib import Path
from typing import NamedTuple, Protocol, runtime_checkable
from uuid import uuid4

import polars as pl
from ditto_analytics.compile_cache import SQLiteCompileCache
from ditto_analytics.evaluation.metrics import orthogonalize
from ditto_analytics.materialization import (
    CompileIdentity,
    DerivedExecutionPlan,
    DerivedExecutionPlanner,
    DerivedMaterializationRequest,
    DerivedMaterializationResult,
    DerivedRunMode,
    DerivedRunStatus,
    DerivedRunTrigger,
)
from ditto_data.models.derived import (
    DerivedCheckpointRecord,
    DerivedDependencyRecord,
    DerivedPartitionRecord,
    DerivedRunRecord,
    DerivedSpecRecord,
    DerivedStateRecord,
    PartitionInfo,
)
from ditto_data.models.publication_safety import DerivedMinimalDQSummaryRecord
from ditto_data.services import (
    DerivedArtifactReader,
    DerivedCatalogService,
    PublicationSafetyRecordService,
)
from ditto_data.services.derived.artifact_persistence_service import (
    ArtifactMetadataParams,
    ArtifactPersistenceService,
)
from ditto_data.services.market_service import MarketService
from ditto_kernel.specs import DerivedSpec, MaterializationProfile

from ditto_app.process.materialization_helpers import (
    build_manifest_record,
    build_minimal_dq_record,
    dependency_refs,
)
from ditto_app.process.materialization_types import (
    DerivedInputProvider,
    InputContext,
    earliest_pending_start,
    hydrate_spec,
    prepare_input_frame,
)
from ditto_app.query._utils import now_iso

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
            raise KeyError(
                "derived spec not found for "
                + f"derived_id={request.derived_id} version={request.version}"
            )
        version_record = self._catalog_service.get_version(
            request.derived_id,
            request.version,
        )
        if version_record is None:
            raise KeyError(
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
            DerivedRunRecord(
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
                status=DerivedRunStatus.RUNNING.value,
                rows_written=0,
                partitions_written=(),
                error_message=None,
                created_at=started_at,
                started_at=started_at,
                finished_at=None,
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
            if spec.materialization_profile == MaterializationProfile.DERIVE:
                self._artifact_writer.write_ephemeral_result(
                    spec=spec_record,
                    run_id=run_id,
                    frame=materialized_frame,
                )
                return self._finalize_derive_run(
                    spec=spec,
                    request=request,
                    plan=plan,
                    run=_RunIdentity(run_id, started_at),
                    rows_written=materialized_frame.height,
                    dependencies=compiled.analysis.dependencies,
                )
            time_key = spec.effective_time_keys[0]
            partitions = self._artifact_writer.write_durable_partitions(
                spec=spec_record,
                time_key=time_key,
                run_id=run_id,
                frame=materialized_frame,
                request_start=request.request_start,
                request_end=request.request_end,
                source_snapshot_id=request.source_snapshot_id,
            )
            self._artifact_writer.write_artifact_metadata(
                ArtifactMetadataParams(
                    spec=spec_record,
                    run_id=run_id,
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
                    run_id=run_id,
                    version=spec.version,
                    frame=materialized_frame,
                )
                self._persist_publication_safety_records(
                    spec=spec,
                    spec_record=spec_record,
                    run_id=run_id,
                    request=request,
                    compile_identity=compiled.compile_identity,
                    partitions=partitions,
                    minimal_dq_record=minimal_dq_record,
                )
            return self._finalize_durable_run(
                spec=spec,
                request=request,
                plan=plan,
                run=_RunIdentity(run_id, started_at),
                frame=materialized_frame,
                partitions=partitions,
                dependencies=compiled.analysis.dependencies,
            )
        except Exception as exc:
            finished_at = now_iso()
            self._catalog_service.save_run(
                DerivedRunRecord(
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
                    status=DerivedRunStatus.FAILED.value,
                    rows_written=0,
                    partitions_written=(),
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
            DerivedRunRecord(
                run_id=run.run_id,
                derived_id=spec.id,
                version=spec.version,
                mode=request.mode.value,
                trigger=request.trigger.value,
                request_start=request.request_start,
                request_end=request.request_end,
                compute_start=plan.compute_start,
                compute_end=plan.compute_end,
                source_snapshot_id=request.source_snapshot_id,
                status=DerivedRunStatus.SUCCESS.value,
                rows_written=rows_written,
                partitions_written=(),
                error_message=None,
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
            DerivedRunRecord(
                run_id=run.run_id,
                derived_id=spec.id,
                version=spec.version,
                mode=request.mode.value,
                trigger=request.trigger.value,
                request_start=request.request_start,
                request_end=request.request_end,
                compute_start=plan.compute_start,
                compute_end=plan.compute_end,
                source_snapshot_id=request.source_snapshot_id,
                status=DerivedRunStatus.SUCCESS.value,
                rows_written=frame.height,
                partitions_written=result.partitions_written,
                error_message=None,
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
            raise RuntimeError("publication record service is not configured")
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


# ===========================================================================
# Cross-section amplification
# ===========================================================================


def apply_cs_amplification(
    *,
    frame: pl.DataFrame,
    instrument_ids: list[int],
    time_keys: tuple[str, ...] = ("trade_date",),
    entity_keys: tuple[str, ...] = ("instrument_id",),
) -> pl.DataFrame:
    """
    Expand a materialized frame to full cross-section coverage.

    Creates a cartesian product of all observed dates (from *time_keys*)
    with every instrument in *instrument_ids*, then left-joins the original
    frame so that missing (date, instrument) pairs appear as null rows.

    This is required for CS factors where the output is only meaningful
    when every instrument is present for each date.
    """
    if frame.is_empty() or not instrument_ids:
        return frame
    key_columns = list(entity_keys) + list(time_keys)
    extra_cols = ["availability_time"] if "availability_time" in frame.columns else []
    unique_dates = frame.select(pl.col(time_keys[0]).unique().sort()).to_series()
    cross = unique_dates.to_frame(time_keys[0]).join(
        pl.DataFrame({entity_keys[0]: instrument_ids}),
        how="cross",
    )
    return cross.join(
        frame.select([*key_columns, "value", *extra_cols]),
        on=key_columns,
        how="left",
    )


# ===========================================================================
# Runtime input provider
# ===========================================================================


_MARKET_DATASET_COLUMNS: dict[str, frozenset[str]] = {
    "market.stock_daily": frozenset(
        {
            "open",
            "high",
            "low",
            "close",
            "pre_close",
            "volume",
            "amount",
        }
    ),
    "market.adj_factor": frozenset({"adj_factor"}),
    "market.stock_status": frozenset(
        {"is_suspended", "suspend_timing", "is_st", "st_type", "list_status"}
    ),
}

_ETF_DATASET_COLUMNS: dict[str, frozenset[str]] = {
    "etf.daily": frozenset(
        {
            "open",
            "high",
            "low",
            "close",
            "pre_close",
            "volume",
            "amount",
            "pct_change",
        }
    ),
}


class RuntimeDerivedInputProvider:
    """Read runtime inputs from local market truth and upstream derived artifacts."""

    def __init__(
        self,
        *,
        catalog_service: DerivedCatalogService,
        market_service: MarketService,
        artifact_root: Path,
        data_root: Path,
    ) -> None:
        self._artifact_reader = DerivedArtifactReader(
            catalog_service=catalog_service,
            artifact_root=artifact_root,
        )
        self._market_service = market_service

    def load_input(self, context: InputContext) -> pl.DataFrame:
        """Load one runtime input frame for the requested dependency set."""
        spec = context.spec
        plan = context.plan
        join_keys = [*spec.entity_keys, *spec.effective_time_keys]

        market_deps, etf_deps, derived_deps = _classify_dependencies(
            context.dependencies,
        )
        adj = _resolve_adj_type(spec)

        start = str(plan.compute_start)
        end = str(plan.compute_end)

        frames = list(
            self._load_market_frames(market_deps, start, end, join_keys),
        )
        frames.extend(self._load_etf_frames(etf_deps, start, end, join_keys, adj))
        frames.extend(self._load_derived_frames(derived_deps, start, end, join_keys))

        if not frames:
            raise NotImplementedError(
                f"Phase 3 input backend not wired for derived_id={spec.id}"
            )
        return _join_frames(frames, join_keys=join_keys)

    def _load_market_frames(
        self,
        deps: dict[str, set[str]],
        start: str,
        end: str,
        join_keys: list[str],
    ) -> list[pl.DataFrame]:
        """Load stock market data frames for classified market dependencies."""
        frames: list[pl.DataFrame] = []
        for dataset_ref, value_columns in deps.items():
            raw = self._fetch_market_data(dataset_ref, start, end)
            if raw is None:
                continue
            frames.append(
                _prepare_market_frame(
                    raw,
                    join_keys=join_keys,
                    value_columns=value_columns,
                    availability_column="trade_date",
                )
            )
        return frames

    def _fetch_market_data(
        self,
        dataset_ref: str,
        start: str,
        end: str,
    ) -> pl.DataFrame | None:
        """Fetch market data for a given dataset reference."""
        if dataset_ref == "market.stock_daily":
            return self._market_service.get_stock_bars(start=start, end=end)
        if dataset_ref == "market.adj_factor":
            return self._market_service.get_adj_factors(start=start, end=end)
        if dataset_ref == "market.stock_status":
            return self._market_service.get_stock_status(start=start, end=end)
        return None

    def _load_etf_frames(
        self,
        deps: dict[str, set[str]],
        start: str,
        end: str,
        join_keys: list[str],
        adj: str,
    ) -> list[pl.DataFrame]:
        """Load ETF data frames for classified ETF dependencies."""
        frames: list[pl.DataFrame] = []
        if "etf.daily" in deps:
            raw = self._market_service.get_etf_bars(
                start=start,
                end=end,
                adj=adj,
            )
            frames.append(
                _prepare_market_frame(
                    raw,
                    join_keys=join_keys,
                    value_columns=deps["etf.daily"],
                    availability_column="trade_date",
                )
            )
        return frames

    def _load_derived_frames(
        self,
        deps: list[str],
        start: str,
        end: str,
        join_keys: list[str],
    ) -> list[pl.DataFrame]:
        """Load upstream derived artifact frames."""
        frames: list[pl.DataFrame] = []
        for derived_id in deps:
            version = self._artifact_reader.resolve_offline_version(derived_id)
            upstream = self._artifact_reader.read_frame(
                derived_id=derived_id,
                version=version,
                start=start,
                end=end,
            )
            frames.append(
                _prepare_derived_frame(
                    upstream,
                    join_keys=join_keys,
                    column_name=derived_id,
                )
            )
        return frames


def _classify_dependencies(
    dependencies: tuple[str, ...],
) -> tuple[
    dict[str, set[str]],
    dict[str, set[str]],
    list[str],
]:
    """Separate dependencies into market, ETF, and derived namespaces."""
    market_dependencies: dict[str, set[str]] = defaultdict(set)
    etf_dependencies: dict[str, set[str]] = defaultdict(set)
    derived_dependencies: list[str] = []

    for dependency in dependencies:
        if dependency.startswith("etf."):
            dataset_ref, column = _resolve_etf_dependency(dependency)
            etf_dependencies[dataset_ref].add(column)
        elif dependency.startswith("market."):
            dataset_ref, column = _resolve_market_dependency(dependency)
            market_dependencies[dataset_ref].add(column)
        elif "." in dependency:
            derived_dependencies.append(dependency)
        else:
            raise NotImplementedError(
                f"Unsupported dependency={dependency} (market.*, etf.*, @derived only)"
            )

    return (
        dict(market_dependencies),
        dict(etf_dependencies),
        derived_dependencies,
    )


def _resolve_adj_type(spec: object) -> str:
    """Extract adj_type from spec's execution_policy, defaulting to 'none'."""
    ep = getattr(spec, "execution_policy", None)
    return ep.adj_type if ep else "none"


def _resolve_market_dependency(dependency: str) -> tuple[str, str]:
    """Resolve a 'market.*' dependency to (dataset_ref, column_name)."""
    column_name = dependency.removeprefix("market.")
    for dataset_ref, columns in _MARKET_DATASET_COLUMNS.items():
        if column_name in columns:
            return (dataset_ref, column_name)
    raise NotImplementedError(f"Unsupported market dependency={dependency}")


def _resolve_etf_dependency(dependency: str) -> tuple[str, str]:
    """Resolve an 'etf.*' dependency to (dataset_ref, column_name)."""
    column_name = dependency.removeprefix("etf.")
    for dataset_ref, columns in _ETF_DATASET_COLUMNS.items():
        if column_name in columns:
            return (dataset_ref, column_name)
    raise NotImplementedError(f"Unsupported ETF dependency={dependency}")


def _prepare_market_frame(
    frame: pl.DataFrame,
    *,
    join_keys: list[str],
    value_columns: set[str],
    availability_column: str,
) -> pl.DataFrame:
    selected_columns = [*join_keys, *sorted(value_columns)]
    existing_columns = [
        column for column in selected_columns if column in frame.columns
    ]
    prepared = frame.select(existing_columns)
    return prepared.with_columns(
        pl.col(availability_column).alias("availability_time__0")
    )


def _prepare_derived_frame(
    frame: pl.DataFrame,
    *,
    join_keys: list[str],
    column_name: str,
) -> pl.DataFrame:
    selected_columns = [*join_keys]
    if "value" in frame.columns:
        selected_columns.append("value")
    if "availability_time" in frame.columns:
        selected_columns.append("availability_time")
    prepared = frame.select(selected_columns)
    renamed: dict[str, str] = {}
    if "value" in prepared.columns:
        renamed["value"] = column_name
    if "availability_time" in prepared.columns:
        renamed["availability_time"] = "availability_time__0"
    return prepared.rename(renamed)


def _join_frames(
    frames: list[pl.DataFrame],
    *,
    join_keys: list[str],
) -> pl.DataFrame:
    base = frames[0]
    availability_columns = ["availability_time__0"]
    for index, frame in enumerate(frames[1:], start=1):
        renamed = {
            column: f"{column}__{index}"
            for column in frame.columns
            if column.startswith("availability_time__")
        }
        next_frame = frame.rename(renamed)
        availability_columns.extend(renamed.values())
        base = base.join(next_frame, on=join_keys, how="left")
    return base.with_columns(
        pl.max_horizontal(
            *(pl.col(column) for column in availability_columns),
        ).alias("availability_time"),
    ).drop(availability_columns)


# ===========================================================================
# Factor orthogonalization service
# ===========================================================================


class FactorOrthogonalizationService:
    """
    Orthogonalize a target factor against control factors.

    Loads the target and control factor artifacts via
    :class:`DerivedArtifactReader`, joins them on
    ``(trade_date, instrument_id)``, and delegates to the pure-function
    :func:`~ditto_analytics.evaluation.metrics.orthogonalize` from
    ``ditto_analytics``.
    """

    def __init__(self, artifact_reader: DerivedArtifactReader) -> None:
        self._artifact_reader = artifact_reader

    def load_and_orthogonalize(
        self,
        target_id: str,
        target_version: int,
        other_factor_ids: list[tuple[str, int]],
        *,
        start: str,
        end: str,
        method: str = "sequential",
    ) -> pl.DataFrame:
        """
        Load factors and compute orthogonalized target values.

        Args:
            target_id: Derived artifact identifier for the target factor.
            target_version: Version of the target artifact.
            other_factor_ids: List of ``(factor_id, version)`` pairs for
                control factors.
            start: Start date (``YYYY-MM-DD``).
            end: End date (``YYYY-MM-DD``).
            method: Orthogonalization method (``"sequential"`` or
                ``"symmetric"``).

        Returns:
            ``pl.DataFrame[trade_date, instrument_id,
            orthogonalized_value]``.

        """
        target_df = self._artifact_reader.read_frame(
            derived_id=target_id,
            version=target_version,
            start=start,
            end=end,
        )

        if not other_factor_ids:
            # No control factors -- return the target values unchanged.
            if target_df.is_empty():
                return pl.DataFrame(
                    schema={
                        "trade_date": pl.Utf8,
                        "instrument_id": pl.Int64,
                        "orthogonalized_value": pl.Float64,
                    },
                )
            return target_df.select(
                pl.col("trade_date"),
                pl.col("instrument_id"),
                pl.col("value").alias("orthogonalized_value"),
            )

        # Load and join control factors.  Each factor gets a
        # ``factor_name`` column so that the orthogonalize() function
        # can distinguish them.
        control_frames: list[pl.DataFrame] = []
        for factor_id, factor_version in other_factor_ids:
            frame = self._artifact_reader.read_frame(
                derived_id=factor_id,
                version=factor_version,
                start=start,
                end=end,
            )
            if frame.is_empty():
                continue
            control_frames.append(
                frame.select(
                    pl.col("trade_date"),
                    pl.col("instrument_id"),
                    pl.col("value"),
                    pl.lit(factor_id).alias("factor_name"),
                ),
            )

        if not control_frames:
            if target_df.is_empty():
                return pl.DataFrame(
                    schema={
                        "trade_date": pl.Utf8,
                        "instrument_id": pl.Int64,
                        "orthogonalized_value": pl.Float64,
                    },
                )
            return target_df.select(
                pl.col("trade_date"),
                pl.col("instrument_id"),
                pl.col("value").alias("orthogonalized_value"),
            )

        factors_df = pl.concat(control_frames)

        return orthogonalize(
            target_df,
            factors_df,
            method=method,
        )
