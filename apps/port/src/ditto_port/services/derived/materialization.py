"""Port-side unified derived materialization orchestration."""

from __future__ import annotations

import platform
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, replace
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Protocol, cast
from uuid import uuid4

import orjson
import polars as pl
from ditto_core.engine.materialization import (
    Analysis,
    CompileIdentity,
    DerivedExecutionPlan,
    DerivedExecutionPlanner,
    DerivedMaterializationRequest,
    DerivedMaterializationResult,
    DerivedRunMode,
    DerivedRunStatus,
    DerivedRunTrigger,
)
from ditto_core.engine.publication_safety import (
    CompatibilityManifest,
    DerivedMinimalDQSummary,
)
from ditto_core.engine.specs import (
    CalendarId,
    DerivedRole,
    DerivedSpec,
    GrainId,
    MaterializationProfile,
)
from ditto_datahub.models.derived import (
    DerivedCheckpointRecord,
    DerivedDependencyRecord,
    DerivedInvalidationRecord,
    DerivedPartitionRecord,
    DerivedRunRecord,
    DerivedSpecRecord,
    DerivedStateRecord,
)
from ditto_datahub.models.publication_safety import (
    CompatibilityManifestRecord,
    DerivedMinimalDQSummaryRecord,
    DerivedShadowSlotRecord,
    JsonDict,
)
from ditto_datahub.services.derived_catalog_service import DerivedCatalogService
from ditto_datahub.services.derived_shadow_slot_service import DerivedShadowSlotService
from ditto_datahub.services.publication_safety_record_service import (
    PublicationSafetyRecordService,
)

from ditto_port.services.derived.compile_cache import SQLiteCompileCacheService

__all__ = [
    "DerivedInputProvider",
    "DerivedMaterializationService",
    "InMemoryDerivedInputProvider",
    "MissingDependencyError",
    "UnavailableDerivedInputProvider",
]


class DerivedInputProvider(Protocol):
    """Input seam used by the materialization service."""

    def load_input(
        self,
        *,
        spec: DerivedSpec,
        request: DerivedMaterializationRequest,
        plan: DerivedExecutionPlan,
        dependencies: tuple[str, ...],
    ) -> pl.DataFrame:
        """Load the raw input frame for one derived request."""
        ...


class InMemoryDerivedInputProvider:
    """Test input provider backed by an in-memory frame mapping."""

    def __init__(self, frames: dict[str, pl.DataFrame]) -> None:
        self._frames = frames

    def load_input(
        self,
        *,
        spec: DerivedSpec,
        request: DerivedMaterializationRequest,
        plan: DerivedExecutionPlan,
        dependencies: tuple[str, ...],
    ) -> pl.DataFrame:
        """Load one in-memory input frame."""
        del request
        del plan
        del dependencies
        frame = self._frames.get(spec.id)
        if frame is None:
            raise KeyError(f"missing input frame for derived_id={spec.id}")
        return frame


class UnavailableDerivedInputProvider:
    """Runtime placeholder until real source loading is wired."""

    def load_input(
        self,
        *,
        spec: DerivedSpec,
        request: DerivedMaterializationRequest,
        plan: DerivedExecutionPlan,
        dependencies: tuple[str, ...],
    ) -> pl.DataFrame:
        """Raise until a runtime source loader is wired."""
        del request
        del plan
        del dependencies
        raise NotImplementedError(
            f"Phase 3 input backend not wired for derived_id={spec.id}"
        )


class DerivedMaterializationService:
    """Compile, execute, and persist one unified derived run."""

    def __init__(
        self,
        *,
        catalog_service: DerivedCatalogService,
        compile_cache_service: SQLiteCompileCacheService,
        input_provider: DerivedInputProvider,
        artifact_root: Path,
        publication_record_service: PublicationSafetyRecordService | None = None,
        shadow_slot_service: DerivedShadowSlotService | None = None,
    ) -> None:
        self._catalog_service = catalog_service
        self._compile_cache_service = compile_cache_service
        self._input_provider = input_provider
        self._artifact_root = Path(artifact_root)
        self._publication_record_service = publication_record_service
        self._shadow_slot_service = shadow_slot_service
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
        spec = _hydrate_spec(spec_record)
        compiled = self._compile_cache_service.get_or_compile(
            spec,
            force_recompile=request.force_recompile,
        )
        earliest_pending = _earliest_pending_start(
            self._catalog_service.list_pending_invalidations(),
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
        started_at = _now_iso()
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
                spec=spec,
                request=request,
                plan=plan,
                dependencies=compiled.analysis.dependencies,
            )
            prepared_frame = _prepare_input_frame(
                frame=input_frame,
                spec=spec,
                dependencies=compiled.analysis.dependencies,
            )
            materialized_frame = prepared_frame.with_columns(
                compiled.expr.alias("value")
            )
            if spec.materialization_profile == MaterializationProfile.DERIVE:
                self._write_ephemeral_result(
                    spec=spec,
                    run_id=run_id,
                    frame=materialized_frame,
                )
                return self._finalize_derive_run(
                    spec=spec,
                    request=request,
                    run_id=run_id,
                    started_at=started_at,
                    rows_written=materialized_frame.height,
                    dependencies=compiled.analysis.dependencies,
                )
            partitions = self._write_durable_artifacts(
                spec=spec,
                run_id=run_id,
                frame=materialized_frame,
                request=request,
                compile_identity=compiled.compile_identity,
                analysis=compiled.analysis,
            )
            minimal_dq_record = None
            if self._publication_record_service is not None:
                minimal_dq_record = _build_minimal_dq_record(
                    spec=spec,
                    run_id=run_id,
                    version=spec.version,
                    frame=materialized_frame,
                )
                self._persist_publication_safety_records(
                    spec=spec,
                    run_id=run_id,
                    request=request,
                    compile_identity=compiled.compile_identity,
                    partitions=partitions,
                    minimal_dq_record=minimal_dq_record,
                )
            return self._finalize_durable_run(
                spec=spec,
                request=request,
                run_id=run_id,
                started_at=started_at,
                frame=materialized_frame,
                partitions=partitions,
                dependencies=compiled.analysis.dependencies,
            )
        except Exception as exc:
            finished_at = _now_iso()
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

    def _finalize_derive_run(
        self,
        *,
        spec: DerivedSpec,
        request: DerivedMaterializationRequest,
        run_id: str,
        started_at: str,
        rows_written: int,
        dependencies: tuple[str, ...],
    ) -> DerivedMaterializationResult:
        finished_at = _now_iso()
        self._persist_dependencies(
            derived_id=spec.id,
            version=spec.version,
            dependencies=dependencies,
            created_at=finished_at,
        )
        result = DerivedMaterializationResult(
            run_id=run_id,
            derived_id=spec.id,
            version=spec.version,
            profile=spec.materialization_profile,
            status=DerivedRunStatus.SUCCESS,
            rows_written=rows_written,
            partitions_written=(),
            coverage_start=request.request_start,
            coverage_end=request.request_end,
        )
        self._catalog_service.save_run(
            DerivedRunRecord(
                run_id=run_id,
                derived_id=spec.id,
                version=spec.version,
                mode=request.mode.value,
                trigger=request.trigger.value,
                request_start=request.request_start,
                request_end=request.request_end,
                compute_start=request.request_start,
                compute_end=request.request_end,
                source_snapshot_id=request.source_snapshot_id,
                status=DerivedRunStatus.SUCCESS.value,
                rows_written=rows_written,
                partitions_written=(),
                error_message=None,
                created_at=started_at,
                started_at=started_at,
                finished_at=finished_at,
            )
        )
        return result

    def _finalize_durable_run(
        self,
        *,
        spec: DerivedSpec,
        request: DerivedMaterializationRequest,
        run_id: str,
        started_at: str,
        frame: pl.DataFrame,
        partitions: tuple[dict[str, str | int], ...],
        dependencies: tuple[str, ...],
    ) -> DerivedMaterializationResult:
        finished_at = _now_iso()
        partition_records = tuple(
            DerivedPartitionRecord(
                run_id=run_id,
                derived_id=spec.id,
                version=spec.version,
                partition_key=cast(str, partition["partition_key"]),
                partition_path=cast(str, partition["partition_path"]),
                row_count=cast(int, partition["row_count"]),
                checksum=cast(str | None, partition["checksum"]),
                written_at=finished_at,
            )
            for partition in partitions
        )
        checkpoint_records = tuple(
            DerivedCheckpointRecord(
                derived_id=spec.id,
                version=spec.version,
                partition_key=cast(str, partition["partition_key"]),
                status="done",
                rows_written=cast(int, partition["row_count"]),
                checksum=cast(str | None, partition["checksum"]),
                error_message=None,
                started_at=started_at,
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
                coverage_start=request.request_start,
                coverage_end=request.request_end,
                watermark=request.request_end,
                latest_run_id=run_id,
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
            run_id=run_id,
            derived_id=spec.id,
            version=spec.version,
            profile=spec.materialization_profile,
            status=DerivedRunStatus.SUCCESS,
            rows_written=frame.height,
            partitions_written=tuple(
                cast(str, partition["partition_key"]) for partition in partitions
            ),
            coverage_start=request.request_start,
            coverage_end=request.request_end,
        )
        self._catalog_service.save_run(
            DerivedRunRecord(
                run_id=run_id,
                derived_id=spec.id,
                version=spec.version,
                mode=request.mode.value,
                trigger=request.trigger.value,
                request_start=request.request_start,
                request_end=request.request_end,
                compute_start=request.request_start,
                compute_end=request.request_end,
                source_snapshot_id=request.source_snapshot_id,
                status=DerivedRunStatus.SUCCESS.value,
                rows_written=frame.height,
                partitions_written=result.partitions_written,
                error_message=None,
                created_at=started_at,
                started_at=started_at,
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
            for dependency_kind, dependency_ref in _dependency_refs(dependencies)
        )
        if records:
            self._catalog_service.save_dependencies(records)

    def _write_ephemeral_result(
        self,
        *,
        spec: DerivedSpec,
        run_id: str,
        frame: pl.DataFrame,
    ) -> None:
        ephemeral_dir = (
            self._artifact_root
            / "derived"
            / "artifacts"
            / spec.materialization_profile.value.lower()
            / spec.id
            / f"v{spec.version}"
            / "_ephemeral"
            / run_id
        )
        ephemeral_dir.mkdir(parents=True, exist_ok=True)
        frame.write_parquet(ephemeral_dir / "result.parquet")

    def _write_durable_artifacts(
        self,
        *,
        spec: DerivedSpec,
        run_id: str,
        frame: pl.DataFrame,
        request: DerivedMaterializationRequest,
        compile_identity: CompileIdentity,
        analysis: Analysis,
    ) -> tuple[dict[str, str | int], ...]:
        version_root = (
            self._artifact_root
            / "derived"
            / "artifacts"
            / spec.materialization_profile.value.lower()
            / spec.id
            / f"v{spec.version}"
        )
        version_root.mkdir(parents=True, exist_ok=True)
        partitions: list[dict[str, str | int]] = []
        trade_date_expr = pl.col(spec.effective_time_keys[0]).cast(pl.Utf8)
        for partition_key in _extract_partition_keys(frame, spec):
            partition_frame = frame.filter(
                trade_date_expr.str.slice(0, 4) == partition_key
            )
            partition_path = version_root / f"{partition_key}.parquet"
            temp_path = version_root / f"{partition_key}.tmp.parquet"
            partition_frame.write_parquet(temp_path)
            temp_path.replace(partition_path)
            checksum = sha256(partition_path.read_bytes()).hexdigest()
            partitions.append(
                {
                    "partition_key": partition_key,
                    "partition_path": str(
                        partition_path.relative_to(self._artifact_root)
                    ),
                    "row_count": partition_frame.height,
                    "checksum": checksum,
                }
            )
        metadata_dir = version_root / "_runs" / run_id
        metadata_dir.mkdir(parents=True, exist_ok=True)
        metadata_dir.joinpath("artifact_metadata.json").write_bytes(
            orjson.dumps(
                {
                    "run_id": run_id,
                    "compile_identity": asdict(compile_identity),
                    "analysis": asdict(analysis),
                    "input_snapshots": [request.source_snapshot_id]
                    if request.source_snapshot_id is not None
                    else [],
                    "coverage": {
                        "start": request.request_start,
                        "end": request.request_end,
                    },
                    "partitions_written": partitions,
                },
                option=orjson.OPT_INDENT_2,
            )
        )
        return tuple(partitions)

    def _persist_publication_safety_records(
        self,
        *,
        spec: DerivedSpec,
        run_id: str,
        request: DerivedMaterializationRequest,
        compile_identity: CompileIdentity,
        partitions: tuple[dict[str, str | int], ...],
        minimal_dq_record: DerivedMinimalDQSummaryRecord,
    ) -> None:
        publication_record_service = self._publication_record_service
        if publication_record_service is None:
            raise RuntimeError("publication record service is not configured")
        manifest_record = _build_manifest_record(
            spec=spec,
            version=spec.version,
            compile_identity=compile_identity,
        )
        publication_record_service.save_manifest(manifest_record)
        publication_record_service.save_minimal_dq_summary(minimal_dq_record)
        self._update_artifact_metadata(
            spec=spec,
            run_id=run_id,
            request=request,
            compile_identity=compile_identity,
            partitions=partitions,
            manifest_record=manifest_record,
            minimal_dq_record=minimal_dq_record,
        )
        shadow_slot_service = self._shadow_slot_service
        if shadow_slot_service is None:
            return
        baseline_version = _resolve_shadow_baseline(
            catalog_service=self._catalog_service,
            derived_id=spec.id,
            candidate_version=spec.version,
        )
        shadow_slot_service.save_slot(
            DerivedShadowSlotRecord(
                derived_id=spec.id,
                candidate_version=spec.version,
                baseline_version=baseline_version,
                activated_at=_now_iso(),
                disabled_at=None,
            )
        )

    def _update_artifact_metadata(
        self,
        *,
        spec: DerivedSpec,
        run_id: str,
        request: DerivedMaterializationRequest,
        compile_identity: CompileIdentity,
        partitions: tuple[dict[str, str | int], ...],
        manifest_record: CompatibilityManifestRecord,
        minimal_dq_record: DerivedMinimalDQSummaryRecord,
    ) -> None:
        metadata_path = (
            self._artifact_root
            / "derived"
            / "artifacts"
            / spec.materialization_profile.value.lower()
            / spec.id
            / f"v{spec.version}"
            / "_runs"
            / run_id
            / "artifact_metadata.json"
        )
        payload = orjson.loads(metadata_path.read_bytes())
        payload["publication"] = {
            "manifest_hash": manifest_record.manifest_hash,
            "compatibility_manifest": manifest_record.payload,
            "minimal_dq_summary": {
                "run_id": minimal_dq_record.run_id,
                "passed": minimal_dq_record.passed,
                "error_count": minimal_dq_record.error_count,
                **minimal_dq_record.payload,
            },
        }
        payload["compile_identity"] = asdict(compile_identity)
        payload["input_snapshots"] = (
            [request.source_snapshot_id]
            if request.source_snapshot_id is not None
            else []
        )
        payload["partitions_written"] = list(partitions)
        metadata_path.write_bytes(
            orjson.dumps(payload, option=orjson.OPT_INDENT_2 | orjson.OPT_SORT_KEYS)
        )


def _hydrate_spec(record: DerivedSpecRecord) -> DerivedSpec:
    payload = record.spec_json
    return DerivedSpec(
        id=str(payload["id"]),
        version=_require_int_payload(payload, "version"),
        role=DerivedRole(str(payload["role"])),
        materialization_profile=MaterializationProfile(
            str(payload["materialization_profile"])
        ),
        expression=str(payload["expression"]),
        entity_keys=tuple(
            cast(list[str], payload.get("entity_keys", ["instrument_id"]))
        ),
        grain=cast(GrainId, str(payload.get("grain", "1d"))),
        time_keys=None
        if payload.get("time_keys") is None
        else tuple(cast(list[str], payload["time_keys"])),
        calendar=cast(CalendarId, str(payload.get("calendar", "cn_stock"))),
        description=None
        if payload.get("description") is None
        else str(payload["description"]),
        pit_required=_optional_bool_payload(payload, "pit_required"),
        normalization_preset=None
        if payload.get("normalization_preset") is None
        else str(payload["normalization_preset"]),
        operator_versions=dict(
            cast(dict[str, str], payload.get("operator_versions", {}))
        ),
    )


def _earliest_pending_start(
    invalidations: Iterable[DerivedInvalidationRecord],
    derived_id: str,
    version: int,
) -> str | None:
    starts = [
        invalidation.affected_start
        for invalidation in invalidations
        if invalidation.derived_id == derived_id and invalidation.version == version
    ]
    if not starts:
        return None
    return min(starts)


def _require_int_payload(payload: Mapping[str, object], key: str) -> int:
    value = payload[key]
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"{key} must be an int")
    return value


def _optional_bool_payload(payload: Mapping[str, object], key: str) -> bool | None:
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, bool):
        raise TypeError(f"{key} must be a bool or null")
    return value


class MissingDependencyError(Exception):
    """Raised when required dependency columns are missing from input data."""

    def __init__(self, missing: list[str], available: list[str]) -> None:
        self.missing = missing
        self.available = available
        super().__init__(
            f"Missing required dependency columns: {missing}. "
            + f"Available columns: {available}"
        )


def _prepare_input_frame(
    *,
    frame: pl.DataFrame,
    spec: DerivedSpec,
    dependencies: tuple[str, ...],
) -> pl.DataFrame:
    """Prepare input data frame, validating all dependencies exist."""
    sort_columns = [*spec.entity_keys, *spec.effective_time_keys]
    prepared = frame.sort(sort_columns)

    missing: list[str] = []
    for dependency in dependencies:
        if dependency not in prepared.columns:
            input_col = _dependency_input_column(dependency)
            if input_col not in prepared.columns:
                missing.append(dependency)

    if missing:
        raise MissingDependencyError(
            missing=missing,
            available=list(prepared.columns),
        )

    return prepared


def _extract_partition_keys(frame: pl.DataFrame, spec: DerivedSpec) -> tuple[str, ...]:
    partition_series = (
        frame.select(pl.col(spec.effective_time_keys[0]).cast(pl.Utf8).str.slice(0, 4))
        .to_series()
        .unique()
        .sort()
    )
    return tuple(str(value) for value in partition_series.to_list())


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _build_manifest_record(
    *,
    spec: DerivedSpec,
    version: int,
    compile_identity: CompileIdentity,
) -> CompatibilityManifestRecord:
    manifest = _build_manifest(spec=spec, compile_identity=compile_identity)
    manifest_hash = _manifest_hash(_manifest_payload(manifest))
    manifest = replace(manifest, manifest_hash=manifest_hash)
    payload = asdict(manifest)
    return CompatibilityManifestRecord(
        derived_id=spec.id,
        version=version,
        manifest_hash=manifest_hash,
        payload=cast(JsonDict, payload),
        created_at=_now_iso(),
    )


def _build_minimal_dq_record(
    *,
    spec: DerivedSpec,
    run_id: str,
    version: int,
    frame: pl.DataFrame,
) -> DerivedMinimalDQSummaryRecord:
    summary = _build_minimal_dq_summary(spec=spec, frame=frame)
    return DerivedMinimalDQSummaryRecord(
        derived_id=spec.id,
        version=version,
        run_id=run_id,
        passed=summary.is_passed(),
        error_count=summary.error_count(),
        payload=cast(JsonDict, asdict(summary)),
        created_at=_now_iso(),
    )


def _build_minimal_dq_summary(
    *,
    spec: DerivedSpec,
    frame: pl.DataFrame,
) -> DerivedMinimalDQSummary:
    primary_key_columns = tuple(
        dict.fromkeys((*spec.entity_keys, *spec.effective_time_keys))
    )
    missing_primary_key_columns = tuple(
        column for column in primary_key_columns if column not in frame.columns
    )
    row_count = frame.height
    failed_checks: list[str] = []
    if row_count <= 0:
        failed_checks.append("row_count_positive")

    null_primary_key_count = 0
    duplicate_key_count = 0
    if missing_primary_key_columns:
        failed_checks.append("primary_keys_present")
    elif row_count > 0:
        null_primary_key_count = _count_null_primary_keys(
            frame=frame,
            primary_key_columns=primary_key_columns,
        )
        duplicate_key_count = _count_duplicate_primary_keys(
            frame=frame,
            primary_key_columns=primary_key_columns,
        )
        if null_primary_key_count > 0:
            failed_checks.append("primary_keys_present")
        if duplicate_key_count > 0:
            failed_checks.append("primary_keys_unique")

    null_value_count = 0
    nan_value_count = 0
    computable_value_count = 0
    if "value" not in frame.columns:
        failed_checks.append("value_column_present")
    else:
        null_value_count = int(frame.select(pl.col("value").is_null().sum()).item())
        nan_value_count = _count_nan_values(frame)
        computable_value_count = _count_computable_values(
            frame=frame,
            null_value_count=null_value_count,
            nan_value_count=nan_value_count,
        )
        if computable_value_count <= 0:
            failed_checks.append("value_has_computable_rows")
        if nan_value_count > 0:
            failed_checks.append("value_has_no_nan")

    return DerivedMinimalDQSummary(
        row_count=row_count,
        primary_key_columns=primary_key_columns,
        missing_primary_key_columns=missing_primary_key_columns,
        null_primary_key_count=null_primary_key_count,
        duplicate_key_count=duplicate_key_count,
        null_value_count=null_value_count,
        nan_value_count=nan_value_count,
        computable_value_count=computable_value_count,
        failed_checks=tuple(failed_checks),
    )


def _count_null_primary_keys(
    *,
    frame: pl.DataFrame,
    primary_key_columns: tuple[str, ...],
) -> int:
    if not primary_key_columns or frame.is_empty():
        return 0
    return int(
        frame.select(
            pl.any_horizontal(
                [pl.col(column).is_null() for column in primary_key_columns]
            ).sum()
        ).item()
    )


def _count_duplicate_primary_keys(
    *,
    frame: pl.DataFrame,
    primary_key_columns: tuple[str, ...],
) -> int:
    if not primary_key_columns or frame.is_empty():
        return 0
    duplicate_rows = (
        frame.group_by(list(primary_key_columns)).len().filter(pl.col("len") > 1)
    )
    if duplicate_rows.is_empty():
        return 0
    return int(duplicate_rows.select((pl.col("len") - 1).sum()).item())


def _count_nan_values(frame: pl.DataFrame) -> int:
    if "value" not in frame.columns:
        return 0
    value_dtype = frame.schema["value"]
    if value_dtype not in (pl.Float32(), pl.Float64()):
        return 0
    return int(frame.select(pl.col("value").is_nan().sum()).item())


def _count_computable_values(
    *,
    frame: pl.DataFrame,
    null_value_count: int,
    nan_value_count: int,
) -> int:
    if "value" not in frame.columns:
        return 0
    return frame.height - null_value_count - nan_value_count


def _build_manifest(
    *,
    spec: DerivedSpec,
    compile_identity: CompileIdentity,
) -> CompatibilityManifest:
    return CompatibilityManifest(
        engine_codegen_version=compile_identity.engine_codegen_version,
        analysis_version=compile_identity.analysis_version,
        polars_version=compile_identity.polars_version,
        expr_serialization_format=compile_identity.expr_serialization_format,
        operator_fingerprint=compile_identity.operator_fingerprint,
        global_compile_flags=_compile_flags_dict(compile_identity.global_compile_flags),
        calendar_id=spec.calendar,
        timezone="Asia/Shanghai",
        time_semantics_version="time-v1",
        python_version=platform.python_version(),
        platform=platform.platform(),
        builder_version="unified-derived-v1",
    )


def _manifest_payload(manifest: CompatibilityManifest) -> JsonDict:
    payload = cast(JsonDict, asdict(manifest))
    payload.pop("manifest_hash", None)
    return payload


def _compile_flags_dict(flags: tuple[str, ...]) -> dict[str, str | int | float | bool]:
    parsed: dict[str, str | int | float | bool] = {}
    for flag in flags:
        if "=" not in flag:
            parsed[flag] = True
            continue
        key, value = flag.split("=", 1)
        parsed[key] = value
    return parsed


def _manifest_hash(payload: JsonDict) -> str:
    serialized = orjson.dumps(payload, option=orjson.OPT_SORT_KEYS)
    return sha256(serialized).hexdigest()


def _resolve_shadow_baseline(
    *,
    catalog_service: DerivedCatalogService,
    derived_id: str,
    candidate_version: int,
) -> int | None:
    primary_online = next(
        (
            record.version
            for record in catalog_service.list_versions(derived_id)
            if (
                record.is_primary
                and record.is_online
                and record.version != candidate_version
            )
        ),
        None,
    )
    if primary_online is not None:
        return primary_online
    return next(
        (
            record.version
            for record in catalog_service.list_versions(derived_id)
            if record.is_primary and record.version != candidate_version
        ),
        None,
    )


def _dependency_refs(
    dependencies: tuple[str, ...],
) -> tuple[tuple[str, str], ...]:
    refs: list[tuple[str, str]] = []
    for dependency in dependencies:
        if dependency.startswith("market."):
            refs.append(("dataset", _market_dependency_ref(dependency)))
            continue
        if "." not in dependency:
            continue
        refs.append(("derived", dependency))
    deduped: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for item in refs:
        if item in seen:
            continue
        deduped.append(item)
        seen.add(item)
    return tuple(deduped)


def _market_dependency_ref(dependency: str) -> str:
    column_name = dependency.removeprefix("market.")
    if column_name in {"open", "high", "low", "close", "pre_close", "volume", "amount"}:
        return "market.stock_daily"
    if column_name == "adj_factor":
        return "market.adj_factor"
    if column_name in {
        "is_suspended",
        "suspend_timing",
        "is_st",
        "st_type",
        "list_status",
    }:
        return "market.stock_status"
    raise NotImplementedError(
        "Unsupported market dependency for durable persistence: "
        + f"dependency={dependency}"
    )


def _dependency_input_column(dependency: str) -> str:
    if dependency.startswith("market."):
        return dependency.removeprefix("market.")
    return dependency
