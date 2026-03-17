"""Port-side unified derived materialization helpers and input providers."""

from __future__ import annotations

import platform
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from hashlib import sha256
from typing import Protocol, cast

import orjson
import polars as pl
from ditto_core.engine.materialization import (
    CompileIdentity,
    DerivedExecutionPlan,
    DerivedMaterializationRequest,
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
    DerivedInvalidationRecord,
    DerivedSpecRecord,
)
from ditto_datahub.models.publication_safety import (
    CompatibilityManifestRecord,
    DerivedMinimalDQSummaryRecord,
    JsonDict,
)
from ditto_datahub.services.derived_catalog_service import DerivedCatalogService

__all__ = [
    "DerivedInputProvider",
    "InMemoryDerivedInputProvider",
    "InputContext",
    "MissingDependencyError",
    "UnavailableDerivedInputProvider",
    "build_manifest_record",
    "build_minimal_dq_record",
    "dependency_refs",
    "earliest_pending_start",
    "hydrate_spec",
    "now_iso",
    "prepare_input_frame",
    "resolve_shadow_baseline",
]


@dataclass(frozen=True)
class InputContext:
    """Encapsulates all parameters needed for input loading."""

    spec: DerivedSpec
    request: DerivedMaterializationRequest
    plan: DerivedExecutionPlan
    dependencies: tuple[str, ...]


class DerivedInputProvider(Protocol):
    """Input seam used by the materialization orchestrator."""

    def load_input(self, context: InputContext) -> pl.DataFrame:
        """Load the raw input frame for one derived request."""
        ...


class InMemoryDerivedInputProvider:
    """Test input provider backed by an in-memory frame mapping."""

    def __init__(self, frames: dict[str, pl.DataFrame]) -> None:
        self._frames = frames

    def load_input(self, context: InputContext) -> pl.DataFrame:
        """Load one in-memory input frame."""
        frame = self._frames.get(context.spec.id)
        if frame is None:
            raise KeyError(f"missing input frame for derived_id={context.spec.id}")
        return frame


class UnavailableDerivedInputProvider:
    """Runtime placeholder until real source loading is wired."""

    def load_input(self, context: InputContext) -> pl.DataFrame:
        """Raise until a runtime source loader is wired."""
        raise NotImplementedError(
            f"Phase 3 input backend not wired for derived_id={context.spec.id}"
        )


class MissingDependencyError(Exception):
    """Raised when required dependency columns are missing from input data."""

    def __init__(self, missing: list[str], available: list[str]) -> None:
        self.missing = missing
        self.available = available
        super().__init__(
            f"Missing required dependency columns: {missing}. "
            + f"Available columns: {available}"
        )


def hydrate_spec(record: DerivedSpecRecord) -> DerivedSpec:
    """Reconstruct a DerivedSpec from its persisted record."""
    payload = record.spec_json
    return DerivedSpec(
        id=str(payload["id"]),
        version=_require_int_payload(payload, "version"),
        role=DerivedRole(str(payload["role"])),
        materialization_profile=_materialization_profile(
            payload["materialization_profile"]
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
        operator_versions=dict(
            cast(dict[str, str], payload.get("operator_versions", {}))
        ),
        universe_id=None
        if payload.get("universe_id") is None
        else str(payload["universe_id"]),
    )


def _materialization_profile(value: object) -> MaterializationProfile:
    return MaterializationProfile(str(value))


def earliest_pending_start(
    invalidations: Iterable[DerivedInvalidationRecord],
    derived_id: str,
    version: int,
) -> str | None:
    """Return the earliest affected_start among pending invalidations."""
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


def prepare_input_frame(
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


def now_iso() -> str:
    """Return current UTC timestamp as ISO string."""
    return datetime.now(UTC).isoformat()


def build_manifest_record(
    *,
    spec: DerivedSpec,
    version: int,
    compile_identity: CompileIdentity,
) -> CompatibilityManifestRecord:
    """Build a persisted manifest record for publication safety."""
    manifest = _build_manifest(spec=spec, compile_identity=compile_identity)
    manifest_hash = _manifest_hash(_manifest_payload(manifest))
    manifest = replace(manifest, manifest_hash=manifest_hash)
    payload = asdict(manifest)
    return CompatibilityManifestRecord(
        derived_id=spec.id,
        version=version,
        manifest_hash=manifest_hash,
        payload=cast(JsonDict, payload),
        created_at=now_iso(),
    )


def build_minimal_dq_record(
    *,
    spec: DerivedSpec,
    run_id: str,
    version: int,
    frame: pl.DataFrame,
) -> DerivedMinimalDQSummaryRecord:
    """Build a minimal DQ summary record for a materialization run."""
    summary = _build_minimal_dq_summary(spec=spec, frame=frame)
    return DerivedMinimalDQSummaryRecord(
        derived_id=spec.id,
        version=version,
        run_id=run_id,
        passed=summary.is_passed(),
        error_count=summary.error_count(),
        payload=cast(JsonDict, asdict(summary)),
        created_at=now_iso(),
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


def resolve_shadow_baseline(
    *,
    catalog_service: DerivedCatalogService,
    derived_id: str,
    candidate_version: int,
) -> int | None:
    """Find the primary online version to use as shadow comparison baseline."""
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


def dependency_refs(
    dependencies: tuple[str, ...],
) -> tuple[tuple[str, str], ...]:
    """Classify each dependency into (kind, ref) pairs for persistence."""
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
