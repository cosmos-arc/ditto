"""Port-side unified derived materialization orchestration."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict
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
    DerivedExecutionPlanner,
    DerivedMaterializationRequest,
    DerivedMaterializationResult,
    DerivedRunMode,
    DerivedRunStatus,
    DerivedRunTrigger,
)
from ditto_core.engine.specs import DerivedRole, DerivedSpec, MaterializationProfile
from ditto_datahub.models.derived import (
    DerivedCheckpointRecord,
    DerivedInvalidationRecord,
    DerivedPartitionRecord,
    DerivedRunRecord,
    DerivedSpecRecord,
    DerivedStateRecord,
)
from ditto_datahub.services.derived_catalog_service import DerivedCatalogService

from ditto_port.services.derived.compile_cache import SQLiteCompileCacheService

__all__ = [
    "DerivedInputProvider",
    "DerivedMaterializationService",
    "InMemoryDerivedInputProvider",
    "UnavailableDerivedInputProvider",
]


class DerivedInputProvider(Protocol):
    """Input seam used by the materialization service."""

    def load_input(
        self,
        *,
        spec: DerivedSpec,
        request: DerivedMaterializationRequest,
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
    ) -> pl.DataFrame:
        """Load one in-memory input frame."""
        del request
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
    ) -> pl.DataFrame:
        """Raise until a runtime source loader is wired."""
        del request
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
    ) -> None:
        self._catalog_service = catalog_service
        self._compile_cache_service = compile_cache_service
        self._input_provider = input_provider
        self._artifact_root = Path(artifact_root)
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
            input_frame = self._input_provider.load_input(spec=spec, request=request)
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
                )
            partitions = self._write_durable_artifacts(
                spec=spec,
                run_id=run_id,
                frame=materialized_frame,
                request=request,
                compile_identity=compiled.compile_identity,
                analysis=compiled.analysis,
            )
            return self._finalize_durable_run(
                spec=spec,
                request=request,
                run_id=run_id,
                started_at=started_at,
                frame=materialized_frame,
                partitions=partitions,
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
    ) -> DerivedMaterializationResult:
        finished_at = _now_iso()
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
        grain=str(payload.get("grain", "1d")),
        time_keys=None
        if payload.get("time_keys") is None
        else tuple(cast(list[str], payload["time_keys"])),
        calendar=str(payload.get("calendar", "cn_stock")),
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


def _prepare_input_frame(
    *,
    frame: pl.DataFrame,
    spec: DerivedSpec,
    dependencies: tuple[str, ...],
) -> pl.DataFrame:
    sort_columns = [*spec.entity_keys, *spec.effective_time_keys]
    prepared = frame.sort(sort_columns)
    key_columns = set(spec.entity_keys) | set(spec.effective_time_keys)
    value_candidates = [
        column for column in prepared.columns if column not in key_columns
    ]
    fallback_column = value_candidates[0] if value_candidates else None
    for dependency in dependencies:
        if dependency in prepared.columns or fallback_column is None:
            continue
        prepared = prepared.with_columns(pl.col(fallback_column).alias(dependency))
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
