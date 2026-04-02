"""App-layer derived materialization services."""

from __future__ import annotations

import platform
from collections import defaultdict, deque
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum
from hashlib import sha256
from pathlib import Path
from typing import Any, NamedTuple, Protocol, cast, runtime_checkable
from uuid import uuid4

import orjson
import polars as pl
from ditto_analytics.compile_cache import SQLiteCompileCache
from ditto_analytics.materialization import (
    CompileIdentity,
    DerivedExecutionPlan,
    DerivedExecutionPlanner,
    DerivedInvalidationEvent,
    DerivedMaterializationRequest,
    DerivedMaterializationResult,
    DerivedRunMode,
    DerivedRunStatus,
    DerivedRunTrigger,
    DerivedVersionStatus,
)
from ditto_data.errors import DerivedNotFoundError, DerivedValidationError
from ditto_datahub.models.derived import (
    DerivedCheckpointRecord,
    DerivedDependencyRecord,
    DerivedInvalidationRecord,
    DerivedPartitionRecord,
    DerivedRunRecord,
    DerivedSpecRecord,
    DerivedStateRecord,
    DerivedVersionRecord,
    PartitionInfo,
)
from ditto_datahub.models.publication_safety import (
    CertificationReportRecord,
    CompatibilityManifestRecord,
    DerivedMinimalDQSummaryRecord,
    DerivedShadowSlotRecord,
    JsonDict,
    JsonValue,
    ShadowDiffReportRecord,
    ShadowTraceRecordRecord,
)
from ditto_datahub.services import (
    DerivedArtifactReader,
    DerivedCatalogService,
    PublicationSafetyRecordService,
)
from ditto_datahub.services.derived.artifact_persistence_service import (
    ArtifactMetadataParams,
    ArtifactPersistenceService,
)
from ditto_datahub.services.derived_shadow_slot_service import DerivedShadowSlotService
from ditto_datahub.services.market_service import MarketService
from ditto_engine.engine.evaluation.metrics import orthogonalize
from ditto_engine.engine.publication_safety import (
    CertificationCheckResult,
    CertificationPack,
    CertificationReport,
    CertificationStage,
    CompatibilityManifest,
    DerivedMinimalDQSummary,
    PublicationSafetySeverity,
    ShadowDiffReport,
    ShadowTraceRecord,
)
from ditto_engine.engine.specs import (
    CalendarId,
    DerivedRole,
    DerivedSpec,
    ExecutionPolicy,
    GrainId,
    MaterializationProfile,
    TimeSpec,
)
from loguru import logger

from ditto_app.query._utils import now_iso

__all__ = [
    # -- cascade_protocol --
    "CASCADE_MAX_RETRY_COUNT",
    "REALTIME_CASCADE_MAX_DEPTH",
    "CascadeDepthExceededError",
    "CascadeStatus",
    # -- input_preparation --
    "DerivedInputProvider",
    # -- materialization_orchestrator --
    "DerivedMaterializationOrchestrator",
    # -- publication --
    "DerivedPublicationFacade",
    # -- factor_orthogonalization_service --
    "FactorOrthogonalizationService",
    "InMemoryDerivedInputProvider",
    "InputContext",
    "InvalidationCascadeOrchestrator",
    "MissingDependencyError",
    "RepairBatchResult",
    # -- runtime_input --
    "RuntimeDerivedInputProvider",
    "UnavailableDerivedInputProvider",
    "UniverseProvider",
    "apply_cs_amplification",
    # -- publication_rules --
    "build_certification_checks",
    # -- manifest_builder --
    "build_manifest_record",
    # -- dq_summary --
    "build_minimal_dq_record",
    "dependency_refs",
    "earliest_pending_start",
    "hydrate_spec",
    "prepare_input_frame",
    "resolve_shadow_baseline",
]


# ===========================================================================
# input_preparation.py
# ---------------------------------------------------------------------------
# Input data preparation for derived materialization.
#
# Provides the ``InputContext`` parameter object, the ``DerivedInputProvider``
# protocol (and two built-in implementations), and the ``prepare_input_frame``
# helper that validates dependency columns against an input frame.
# ===========================================================================


# ---------------------------------------------------------------------------
# InputContext & DerivedInputProvider
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# MissingDependencyError
# ---------------------------------------------------------------------------


class MissingDependencyError(Exception):
    """Raised when required dependency columns are missing from input data."""

    def __init__(self, missing: list[str], available: list[str]) -> None:
        self.missing = missing
        self.available = available
        super().__init__(
            f"Missing required dependency columns: {missing}. "
            + f"Available columns: {available}"
        )


# ---------------------------------------------------------------------------
# Spec hydration
# ---------------------------------------------------------------------------


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
        time_spec=_time_spec(payload.get("time_spec")),
        operator_versions=dict(
            cast(dict[str, str], payload.get("operator_versions", {}))
        ),
        universe_id=None
        if payload.get("universe_id") is None
        else str(payload["universe_id"]),
        execution_policy=_execution_policy(payload.get("execution_policy")),
    )


def _materialization_profile(value: object) -> MaterializationProfile:
    return MaterializationProfile(str(value))


def _time_spec(raw: object) -> TimeSpec | None:
    if raw is None:
        return None
    d = cast(dict[str, Any], raw)
    return TimeSpec(
        event_time_key=str(d["event_time_key"]),
        availability_time_key=str(d["availability_time_key"])
        if d.get("availability_time_key")
        else None,
    )


def _execution_policy(raw: object) -> ExecutionPolicy:
    if raw is None:
        return ExecutionPolicy()
    d = cast(dict[str, Any], raw)
    return ExecutionPolicy(
        pit_required=bool(d.get("pit_required", True)),
        normalization_preset=str(d.get("normalization_preset", "default")),
        adj_type=str(d.get("adj_type", "none")),
    )


def _require_int_payload(payload: Mapping[str, object], key: str) -> int:
    value = payload[key]
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"{key} must be an int")
    return value


# ---------------------------------------------------------------------------
# Invalidation helpers
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Input frame preparation
# ---------------------------------------------------------------------------


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


def _dependency_input_column(dependency: str) -> str:
    if dependency.startswith("market."):
        return dependency.removeprefix("market.")
    return dependency


# ===========================================================================
# dq_summary.py
# ---------------------------------------------------------------------------
# Minimal DQ summary computation for derived materialization.
#
# Builds a ``DerivedMinimalDQSummaryRecord`` from a materialized frame,
# checking primary-key integrity, value coverage, and basic distribution
# statistics.
# ===========================================================================


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


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
    coverage_rate = 0.0
    value_mean = 0.0
    value_std = 0.0
    value_skewness = 0.0
    value_jump_rate = 0.0
    max_consecutive_nulls = 0
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

        # Enhanced DQ statistics (PUB-PB-1)
        coverage_rate = computable_value_count / row_count if row_count > 0 else 0.0
        value_stats = _compute_value_statistics(frame)
        value_mean = value_stats["mean"]
        value_std = value_stats["std"]
        value_skewness = value_stats["skewness"]
        value_jump_rate = _compute_value_jump_rate(frame, value_stats["std"])
        max_consecutive_nulls = _compute_max_consecutive_nulls(
            frame,
            spec.effective_time_keys,
        )

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
        coverage_rate=coverage_rate,
        value_mean=value_mean,
        value_std=value_std,
        value_skewness=value_skewness,
        distribution_drift=None,
        value_jump_rate=value_jump_rate,
        max_consecutive_nulls=max_consecutive_nulls,
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


def _compute_value_statistics(frame: pl.DataFrame) -> dict[str, float]:
    """Compute mean, std, and skewness of non-null, non-NaN values."""
    clean = frame.select(
        pl.col("value").drop_nulls().drop_nans().alias("v"),
    )
    if clean.is_empty():
        return {"mean": 0.0, "std": 0.0, "skewness": 0.0}

    mean_val = float(clean.select(pl.col("v").mean()).item() or 0.0)
    std_val = float(clean.select(pl.col("v").std(ddof=1)).item() or 0.0)
    # Skewness = E[((x - mean) / std)^3]
    if std_val > 0:
        skewness = float(
            clean.select(
                ((pl.col("v") - mean_val) / std_val).pow(3).mean(),
            ).item()
            or 0.0,
        )
    else:
        skewness = 0.0
    return {"mean": mean_val, "std": std_val, "skewness": skewness}


def _compute_value_jump_rate(frame: pl.DataFrame, value_std: float) -> float:
    """
    Compute the fraction of jumps exceeding 3 * std in consecutive values.

    For each entity, compute pct_change between consecutive time-ordered rows.
    A "jump" is ``abs(pct_change) > 3 * value_std``.
    """
    if value_std <= 0:
        return 0.0

    threshold = 3.0 * value_std
    time_keys = [col for col in frame.columns if col in ("trade_date", "date", "time")]
    entity_keys = [
        col for col in frame.columns if col in ("instrument_id", "entity_id", "code")
    ]

    if not time_keys or not entity_keys:
        return 0.0

    # Filter to computable rows and sort
    computable = frame.filter(
        pl.col("value").is_not_null() & pl.col("value").is_not_nan(),
    ).sort(entity_keys + time_keys)

    _MIN_PCT_CHANGE_OBS = 2
    if computable.height < _MIN_PCT_CHANGE_OBS:
        return 0.0

    # Compute pct_change per entity
    pct_changes = computable.group_by(entity_keys[0], maintain_order=True).agg(
        pct=pl.col("value").pct_change(1).drop_nulls(),
    )

    if pct_changes.is_empty():
        return 0.0

    # Count jumps across all entities
    all_pct = pct_changes.select(pl.col("pct").explode())
    if all_pct.is_empty():
        return 0.0

    n_total = all_pct.height
    n_jumps = int(all_pct.filter(pl.col("pct").abs() > threshold).height)
    return n_jumps / n_total if n_total > 0 else 0.0


def _compute_max_consecutive_nulls(
    frame: pl.DataFrame,
    time_keys: tuple[str, ...] | None,
) -> int:
    """
    Compute the longest streak of consecutive null values.

    Scans the frame sorted by entity then time, counting the maximum run of
    consecutive null "value" entries within each entity.
    """
    entity_keys = [
        col for col in frame.columns if col in ("instrument_id", "entity_id", "code")
    ]
    effective_time_keys = list(time_keys or [])
    # Fall back to any known time column
    if not effective_time_keys:
        for col in ("trade_date", "date", "time"):
            if col in frame.columns:
                effective_time_keys = [col]
                break

    if not entity_keys or not effective_time_keys:
        # No entity/time keys: count consecutive nulls in order
        if "value" not in frame.columns or frame.is_empty():
            return 0
        is_null_series = frame.select(pl.col("value").is_null()).to_series()
        return _max_consecutive_true(is_null_series)

    sort_keys = entity_keys + effective_time_keys
    sorted_frame = frame.sort(sort_keys)

    # Per entity, compute max consecutive nulls
    max_streak = 0
    for entity_df in sorted_frame.group_by(entity_keys[0]):
        group = entity_df[1]
        if "value" not in group.columns:
            continue
        is_null_series = group.select(pl.col("value").is_null()).to_series()
        streak = _max_consecutive_true(is_null_series)
        max_streak = max(max_streak, streak)

    return max_streak


def _max_consecutive_true(series: pl.Series) -> int:
    """Return the longest consecutive run of True values in a boolean series."""
    if series.is_empty():
        return 0
    current = 0
    max_run = 0
    for val in series.to_list():
        if val is True or val == 1:
            current += 1
            max_run = max(max_run, current)
        else:
            current = 0
    return max_run


# ===========================================================================
# manifest_builder.py
# ---------------------------------------------------------------------------
# Compatibility manifest and dependency tracking for derived materialization.
#
# Builds ``CompatibilityManifestRecord`` instances for publication safety and
# provides helpers for shadow baseline resolution and dependency reference
# classification.
# ===========================================================================


# ---------------------------------------------------------------------------
# Manifest building
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Shadow baseline
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Dependency reference classification
# ---------------------------------------------------------------------------


def dependency_refs(
    dependencies: tuple[str, ...],
) -> tuple[tuple[str, str], ...]:
    """Classify each dependency into (kind, ref) pairs for persistence."""
    refs: list[tuple[str, str]] = []
    for dependency in dependencies:
        if dependency.startswith("market."):
            refs.append(("dataset", _market_dependency_ref(dependency)))
            continue
        if dependency.startswith("etf."):
            refs.append(("dataset", _etf_dependency_ref(dependency)))
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


# ---------------------------------------------------------------------------
# Internal helpers (manifest_builder)
# ---------------------------------------------------------------------------


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


_ETF_DAILY_COLUMNS = frozenset(
    {"open", "high", "low", "close", "pre_close", "volume", "amount", "pct_change"}
)


def _etf_dependency_ref(dependency: str) -> str:
    column_name = dependency.removeprefix("etf.")
    if column_name in _ETF_DAILY_COLUMNS:
        return "etf.daily"
    raise NotImplementedError(
        "Unsupported ETF dependency for durable persistence: "
        + f"dependency={dependency}"
    )


# ===========================================================================
# publication.py
# ---------------------------------------------------------------------------
# Port facade for derived publication orchestration.
# ===========================================================================

_VALUE_DIFF_TOLERANCE = 1e-12


class DerivedPublicationFacade:
    """Use-case facade for publication lifecycle and safety gates."""

    def __init__(
        self,
        *,
        catalog_service: DerivedCatalogService,
        artifact_reader: DerivedArtifactReader,
        publication_record_service: PublicationSafetyRecordService,
        shadow_slot_service: DerivedShadowSlotService,
    ) -> None:
        self._catalog_service = catalog_service
        self._artifact_reader = artifact_reader
        self._publication_record_service = publication_record_service
        self._shadow_slot_service = shadow_slot_service

    def shadow_publish(
        self,
        *,
        derived_id: str,
        candidate_version: int,
        baseline_version: int | None = None,
    ) -> DerivedShadowSlotRecord:
        """Register or update the active shadow candidate for one derived id."""
        self._require_version(derived_id, candidate_version)
        resolved_baseline = baseline_version or self._resolve_baseline_version(
            derived_id,
            candidate_version,
        )
        slot = DerivedShadowSlotRecord(
            derived_id=derived_id,
            candidate_version=candidate_version,
            baseline_version=resolved_baseline,
            activated_at=now_iso(),
            disabled_at=None,
        )
        self._shadow_slot_service.save_slot(slot)
        return slot

    def run_shadow_compare(
        self,
        *,
        derived_id: str,
        start: str,
        end: str,
        candidate_version: int | None = None,
        baseline_version: int | None = None,
    ) -> ShadowDiffReport:
        """Compare candidate and baseline artifacts across one audit window."""
        slot = self._resolve_slot(
            derived_id=derived_id,
            candidate_version=candidate_version,
            baseline_version=baseline_version,
        )
        if slot.baseline_version is None:
            raise DerivedNotFoundError(derived_id=derived_id)
        candidate_manifest = self._require_manifest(
            derived_id=derived_id,
            version=slot.candidate_version,
        )
        baseline_manifest = self._require_manifest(
            derived_id=derived_id,
            version=slot.baseline_version,
        )
        candidate_frame = self._artifact_reader.read_frame(
            derived_id=derived_id,
            version=slot.candidate_version,
            start=start,
            end=end,
        )
        baseline_frame = self._artifact_reader.read_frame(
            derived_id=derived_id,
            version=slot.baseline_version,
            start=start,
            end=end,
        )
        report = _build_shadow_diff_report(
            derived_id=derived_id,
            candidate_version=slot.candidate_version,
            baseline_version=slot.baseline_version,
            candidate_frame=candidate_frame,
            baseline_frame=baseline_frame,
            candidate_manifest_hash=candidate_manifest.manifest_hash,
            baseline_manifest_hash=baseline_manifest.manifest_hash,
        )
        traces = _build_shadow_traces(
            report=report,
            candidate_frame=candidate_frame,
            baseline_frame=baseline_frame,
        )
        self._publication_record_service.save_shadow_report(
            _to_shadow_report_record(report),
            tuple(_to_shadow_trace_record(derived_id, trace) for trace in traces),
        )
        return report

    def certify(
        self,
        *,
        derived_id: str,
        version: int,
        stage: CertificationStage,
    ) -> CertificationReport:
        """Run one certification gate for a candidate version."""
        spec_record = self._require_spec(derived_id, version)
        manifest_record = self._require_manifest(derived_id=derived_id, version=version)
        manifest = _hydrate_manifest(manifest_record)
        minimal_dq_record = (
            self._publication_record_service.get_latest_minimal_dq_summary(
                derived_id,
                version,
            )
        )
        slot = self._shadow_slot_service.get_active_slot(derived_id)
        shadow_report_record = None
        if (
            slot is not None
            and slot.candidate_version == version
            and slot.baseline_version is not None
        ):
            shadow_report_record = (
                self._publication_record_service.get_latest_shadow_report(
                    derived_id,
                    slot.candidate_version,
                    slot.baseline_version,
                )
            )
        role = DerivedRole(spec_record.role)
        materialization_profile = MaterializationProfile(
            spec_record.materialization_profile
        )
        checks = build_certification_checks(
            stage=stage,
            role=role,
            materialization_profile=materialization_profile,
            manifest=manifest,
            minimal_dq_record=minimal_dq_record,
            shadow_report_record=shadow_report_record,
        )
        pack = CertificationPack(
            pack_id=(
                f"pack-{spec_record.role.lower()}"
                + f"-{spec_record.materialization_profile.lower()}"
                + f"-{stage.value}"
            ),
            role=role,
            materialization_profile=materialization_profile,
            stage=stage,
            check_names=tuple(check.name for check in checks),
        )
        report = CertificationReport(
            report_id=f"cert-{uuid4().hex[:12]}",
            pack=pack,
            derived_id=derived_id,
            version=version,
            checks=checks,
            manifest_hash=manifest_record.manifest_hash,
            shadow_diff_report_id=None
            if shadow_report_record is None
            else shadow_report_record.report_id,
            created_at=now_iso(),
        )
        self._publication_record_service.save_certification_report(
            CertificationReportRecord(
                report_id=report.report_id,
                derived_id=derived_id,
                version=version,
                stage=stage.value,
                pack_id=pack.pack_id,
                manifest_hash=manifest_record.manifest_hash,
                payload=_certification_payload(report),
                created_at=report.created_at,
            )
        )
        return report

    def promote(
        self,
        *,
        derived_id: str,
        candidate_version: int,
    ) -> DerivedVersionRecord:
        """Promote one candidate version to the online primary slot."""
        self._require_promotable_candidate(
            derived_id=derived_id,
            candidate_version=candidate_version,
        )
        promoted_at = now_iso()
        self._move_primary_pointer(
            derived_id=derived_id,
            target_version=candidate_version,
            target_status=DerivedVersionStatus.PUBLISHED,
            updated_at=promoted_at,
        )
        self._shadow_slot_service.disable_slot(derived_id, promoted_at)
        promoted = self._catalog_service.get_version(derived_id, candidate_version)
        if promoted is None:
            raise DerivedNotFoundError(derived_id=derived_id, version=candidate_version)
        return promoted

    def rollback(
        self,
        *,
        derived_id: str,
        target_version: int,
    ) -> DerivedVersionRecord:
        """Move the primary pointer back to one already-published version."""
        target = self._require_version(derived_id, target_version)
        if target.status != DerivedVersionStatus.PUBLISHED:
            raise DerivedValidationError(
                "rollback target must already be published: "
                + f"id={derived_id} v={target_version}",
                derived_id=derived_id,
            )
        rolled_back_at = now_iso()
        self._move_primary_pointer(
            derived_id=derived_id,
            target_version=target_version,
            target_status=target.status,
            updated_at=rolled_back_at,
        )
        rolled_back = self._catalog_service.get_version(derived_id, target_version)
        if rolled_back is None:
            raise DerivedNotFoundError(derived_id=derived_id, version=target_version)
        return rolled_back

    def deprecate(
        self,
        *,
        derived_id: str,
        version: int,
    ) -> DerivedVersionRecord:
        """Mark one published non-primary version as deprecated and offline."""
        version_record = self._require_version(derived_id, version)
        if version_record.status != DerivedVersionStatus.PUBLISHED:
            raise DerivedValidationError(
                "only published versions can be deprecated: "
                + f"id={derived_id} v={version}",
                derived_id=derived_id,
            )
        if version_record.is_primary:
            raise DerivedValidationError(
                "primary must be rolled back before deprecate: "
                + f"id={derived_id} v={version}",
            )
        deprecated_at = now_iso()
        self._catalog_service.save_version(
            DerivedVersionRecord(
                derived_id=version_record.derived_id,
                version=version_record.version,
                status=DerivedVersionStatus.DEPRECATED,
                engine_version=version_record.engine_version,
                is_online=False,
                is_primary=False,
                created_at=version_record.created_at,
                updated_at=deprecated_at,
            )
        )
        deprecated = self._catalog_service.get_version(derived_id, version)
        if deprecated is None:
            raise DerivedNotFoundError(derived_id=derived_id, version=version)
        return deprecated

    def _resolve_slot(
        self,
        *,
        derived_id: str,
        candidate_version: int | None,
        baseline_version: int | None,
    ) -> DerivedShadowSlotRecord:
        if candidate_version is None and baseline_version is None:
            slot = self._shadow_slot_service.get_active_slot(derived_id)
            if slot is None:
                raise DerivedNotFoundError(derived_id=derived_id)
            return slot
        if candidate_version is None:
            raise DerivedValidationError(
                "candidate_version is required when baseline_version is set"
            )
        self._require_version(derived_id, candidate_version)
        if baseline_version is not None:
            self._require_version(derived_id, baseline_version)
        return DerivedShadowSlotRecord(
            derived_id=derived_id,
            candidate_version=candidate_version,
            baseline_version=baseline_version,
            activated_at=now_iso(),
            disabled_at=None,
        )

    def _resolve_baseline_version(
        self,
        derived_id: str,
        candidate_version: int,
    ) -> int | None:
        primary_online = next(
            (
                record.version
                for record in self._catalog_service.list_versions(derived_id)
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
                for record in self._catalog_service.list_versions(derived_id)
                if record.is_primary and record.version != candidate_version
            ),
            None,
        )

    def _require_promotable_candidate(
        self,
        *,
        derived_id: str,
        candidate_version: int,
    ) -> DerivedShadowSlotRecord:
        self._require_version(derived_id, candidate_version)
        latest_run = self._catalog_service.get_latest_run(derived_id, candidate_version)
        if latest_run is None or latest_run.status != DerivedRunStatus.SUCCESS:
            raise DerivedValidationError(
                "candidate version is not materialized: "
                + f"id={derived_id} v={candidate_version}",
                derived_id=derived_id,
            )
        manifest_record = self._require_manifest(
            derived_id=derived_id,
            version=candidate_version,
        )
        manifest = _hydrate_manifest(manifest_record)
        if not manifest.is_complete():
            raise DerivedValidationError(
                "candidate manifest is incomplete: "
                + f"id={derived_id} v={candidate_version}",
                derived_id=derived_id,
            )
        slot = self._shadow_slot_service.get_active_slot(derived_id)
        if slot is None or slot.candidate_version != candidate_version:
            raise DerivedValidationError(
                "active shadow slot missing: "
                + f"id={derived_id} v={candidate_version}",
                derived_id=derived_id,
            )
        if slot.baseline_version is None:
            raise DerivedValidationError(
                f"shadow baseline missing for {derived_id}",
                derived_id=derived_id,
            )
        shadow_report = self._publication_record_service.get_latest_shadow_report(
            derived_id,
            candidate_version,
            slot.baseline_version,
        )
        if shadow_report is None or shadow_report.error_count > 0:
            raise DerivedValidationError(
                "shadow compare not publishable: "
                + f"id={derived_id} v={candidate_version}",
                derived_id=derived_id,
            )
        certification = (
            self._publication_record_service.get_latest_certification_report(
                derived_id,
                candidate_version,
                CertificationStage.PUBLISH_READY.value,
            )
        )
        if certification is None or certification.payload.get("passed") is not True:
            raise DerivedValidationError(
                "publish_ready gate has not passed: "
                + f"id={derived_id} v={candidate_version}",
                derived_id=derived_id,
            )
        return slot

    def _move_primary_pointer(
        self,
        *,
        derived_id: str,
        target_version: int,
        target_status: str,
        updated_at: str,
    ) -> None:
        for version_record in self._catalog_service.list_versions(derived_id):
            if version_record.version == target_version:
                self._catalog_service.save_version(
                    DerivedVersionRecord(
                        derived_id=version_record.derived_id,
                        version=version_record.version,
                        status=target_status,
                        engine_version=version_record.engine_version,
                        is_online=True,
                        is_primary=True,
                        created_at=version_record.created_at,
                        updated_at=updated_at,
                    )
                )
                continue
            if version_record.is_primary:
                self._catalog_service.save_version(
                    DerivedVersionRecord(
                        derived_id=version_record.derived_id,
                        version=version_record.version,
                        status=version_record.status,
                        engine_version=version_record.engine_version,
                        is_online=version_record.is_online,
                        is_primary=False,
                        created_at=version_record.created_at,
                        updated_at=updated_at,
                    )
                )

    def _require_spec(
        self,
        derived_id: str,
        version: int,
    ) -> DerivedSpecRecord:
        spec_record = self._catalog_service.get_spec(derived_id, version)
        if spec_record is None:
            raise DerivedNotFoundError(derived_id=derived_id, version=version)
        return spec_record

    def _require_version(self, derived_id: str, version: int) -> DerivedVersionRecord:
        version_record = self._catalog_service.get_version(derived_id, version)
        if version_record is None:
            raise DerivedNotFoundError(derived_id=derived_id, version=version)
        return version_record

    def _require_manifest(
        self,
        *,
        derived_id: str,
        version: int,
    ) -> CompatibilityManifestRecord:
        manifest_record = self._publication_record_service.get_manifest(
            derived_id,
            version,
        )
        if manifest_record is None:
            raise DerivedNotFoundError(derived_id=derived_id, version=version)
        return manifest_record


# ---------------------------------------------------------------------------
# Internal helpers (publication)
# ---------------------------------------------------------------------------


def _build_shadow_diff_report(
    *,
    derived_id: str,
    candidate_version: int,
    baseline_version: int,
    candidate_frame: pl.DataFrame,
    baseline_frame: pl.DataFrame,
    candidate_manifest_hash: str,
    baseline_manifest_hash: str,
) -> ShadowDiffReport:
    candidate_prepared = _prepare_compare_frame(candidate_frame, "candidate")
    baseline_prepared = _prepare_compare_frame(baseline_frame, "baseline")
    combined = candidate_prepared.join(
        baseline_prepared,
        on=["instrument_id", "trade_date"],
        how="full",
        coalesce=True,
    ).sort(["instrument_id", "trade_date"])
    schema_match = tuple(candidate_frame.columns) == tuple(baseline_frame.columns)
    diff_count = combined.filter(_value_mismatch_expr()).height
    request_count = combined.height
    coverage_delta = _coverage_delta(
        candidate_count=candidate_frame.height,
        baseline_count=baseline_frame.height,
    )
    error_count = sum(
        int(condition)
        for condition in (
            not schema_match,
            diff_count > 0,
            candidate_frame.height != baseline_frame.height,
        )
    )
    return ShadowDiffReport(
        report_id=f"diff-{uuid4().hex[:12]}",
        derived_id=derived_id,
        candidate_version=candidate_version,
        baseline_version=baseline_version,
        request_count=request_count,
        sample_count=request_count,
        schema_match=schema_match,
        value_diff_rate=0.0 if request_count == 0 else diff_count / request_count,
        coverage_delta=coverage_delta,
        freshness_delta=None,
        latency_p50_delta=None,
        latency_p95_delta=None,
        fallback_ratio_delta=None,
        error_count=error_count,
        warning_count=0,
        info_count=0,
        candidate_manifest_hash=candidate_manifest_hash,
        baseline_manifest_hash=baseline_manifest_hash,
        created_at=now_iso(),
    )


def _build_shadow_traces(
    *,
    report: ShadowDiffReport,
    candidate_frame: pl.DataFrame,
    baseline_frame: pl.DataFrame,
) -> tuple[ShadowTraceRecord, ...]:
    candidate_prepared = _prepare_compare_frame(candidate_frame, "candidate")
    baseline_prepared = _prepare_compare_frame(baseline_frame, "baseline")
    combined = candidate_prepared.join(
        baseline_prepared,
        on=["instrument_id", "trade_date"],
        how="full",
        coalesce=True,
    ).sort(["instrument_id", "trade_date"])
    mismatches = combined.filter(_value_mismatch_expr()).head(20)
    traces: list[ShadowTraceRecord] = []
    for row in mismatches.iter_rows(named=True):
        traces.append(
            ShadowTraceRecord(
                trace_id=f"trace-{uuid4().hex[:12]}",
                report_id=report.report_id,
                request_context={
                    "instrument_id": int(row["instrument_id"]),
                    "trade_date": str(row["trade_date"]),
                },
                candidate_value=row["candidate_value"],
                baseline_value=row["baseline_value"],
                diff_category="value_mismatch",
                candidate_manifest_hash=report.candidate_manifest_hash,
                baseline_manifest_hash=report.baseline_manifest_hash,
                sampled_at=report.created_at,
            )
        )
    return tuple(traces)


def _prepare_compare_frame(frame: pl.DataFrame, prefix: str) -> pl.DataFrame:
    availability_expr = (
        pl.col("availability_time")
        if "availability_time" in frame.columns
        else pl.col("trade_date")
    )
    return frame.select(
        pl.col("instrument_id").cast(pl.Int64),
        pl.col("trade_date"),
        pl.col("value").cast(pl.Float64).alias(f"{prefix}_value"),
        availability_expr.alias(f"{prefix}_availability_time"),
    )


def _value_mismatch_expr() -> pl.Expr:
    return (
        pl.col("candidate_value").is_null() != pl.col("baseline_value").is_null()
    ) | (
        (pl.col("candidate_value") - pl.col("baseline_value")).abs()
        > _VALUE_DIFF_TOLERANCE
    )


def _coverage_delta(*, candidate_count: int, baseline_count: int) -> float:
    if baseline_count == 0:
        return 0.0 if candidate_count == 0 else 1.0
    return (candidate_count - baseline_count) / baseline_count


def _to_shadow_report_record(report: ShadowDiffReport) -> ShadowDiffReportRecord:
    payload = cast(JsonDict, asdict(report))
    return ShadowDiffReportRecord(
        report_id=report.report_id,
        derived_id=report.derived_id,
        candidate_version=report.candidate_version,
        baseline_version=report.baseline_version,
        error_count=report.error_count,
        warning_count=report.warning_count,
        info_count=report.info_count,
        payload=payload,
        created_at=report.created_at,
    )


def _to_shadow_trace_record(
    derived_id: str,
    trace: ShadowTraceRecord,
) -> ShadowTraceRecordRecord:
    return ShadowTraceRecordRecord(
        trace_id=trace.trace_id,
        report_id=trace.report_id,
        derived_id=derived_id,
        payload=cast(JsonDict, asdict(trace)),
        sampled_at=trace.sampled_at,
    )


def _certification_payload(report: CertificationReport) -> JsonDict:
    return cast(
        JsonDict,
        {
            "pack": {
                "pack_id": report.pack.pack_id,
                "role": report.pack.role.value,
                "materialization_profile": report.pack.materialization_profile.value,
                "stage": report.pack.stage.value,
                "check_names": list(report.pack.check_names),
            },
            "checks": [
                {
                    "name": check.name,
                    "severity": check.severity.value,
                    "passed": check.passed,
                    "message": check.message,
                    "metric_value": check.metric_value,
                    "threshold_value": check.threshold_value,
                }
                for check in report.checks
            ],
            "passed": report.is_passed(),
            "check_counts": {
                severity.value: count
                for severity, count in report.check_counts().items()
            },
            "shadow_diff_report_id": report.shadow_diff_report_id,
        },
    )


def _hydrate_manifest(record: CompatibilityManifestRecord) -> CompatibilityManifest:
    payload = record.payload
    return CompatibilityManifest(
        engine_codegen_version=_optional_manifest_str(
            payload,
            "engine_codegen_version",
        ),
        analysis_version=_optional_manifest_str(payload, "analysis_version"),
        polars_version=_optional_manifest_str(payload, "polars_version"),
        expr_serialization_format=_optional_manifest_str(
            payload,
            "expr_serialization_format",
        ),
        operator_fingerprint=_optional_manifest_str(payload, "operator_fingerprint"),
        global_compile_flags=_optional_compile_flags(
            payload.get("global_compile_flags"),
        ),
        calendar_id=_optional_manifest_str(payload, "calendar_id"),
        timezone=_optional_manifest_str(payload, "timezone"),
        time_semantics_version=_optional_manifest_str(
            payload,
            "time_semantics_version",
        ),
        python_version=_optional_manifest_str(payload, "python_version"),
        platform=_optional_manifest_str(payload, "platform"),
        builder_version=_optional_manifest_str(payload, "builder_version"),
        manifest_hash=_optional_manifest_str(payload, "manifest_hash"),
    )


def _optional_manifest_str(payload: JsonDict, key: str) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError(f"{key} must be a string or null")
    return value


def _optional_compile_flags(
    value: JsonValue | None,
) -> dict[str, str | int | float | bool] | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise TypeError("global_compile_flags must be a JSON object or null")
    compile_flags: dict[str, str | int | float | bool] = {}
    for key, item in value.items():
        if not isinstance(item, bool | int | float | str):
            raise TypeError("global_compile_flags values must be primitive JSON values")
        compile_flags[key] = item
    return compile_flags


# ===========================================================================
# publication_rules.py
# ---------------------------------------------------------------------------
# Rule builder for derived publication certification checks.
# ===========================================================================


def build_certification_checks(
    *,
    stage: CertificationStage,
    role: DerivedRole,
    materialization_profile: MaterializationProfile,
    manifest: CompatibilityManifest,
    minimal_dq_record: DerivedMinimalDQSummaryRecord | None,
    shadow_report_record: ShadowDiffReportRecord | None,
) -> tuple[CertificationCheckResult, ...]:
    """Build certification checks for one role/profile/stage combination."""
    common_checks = (
        _pub_build_minimal_dq_check(minimal_dq_record),
        _pub_build_manifest_check(manifest),
    )
    if stage == CertificationStage.SHADOW_READY:
        return common_checks

    checks = [
        *common_checks,
        _pub_build_shadow_ready_gate_check(common_checks),
        *_pub_build_diff_or_audit_checks(
            materialization_profile=materialization_profile,
            shadow_report_record=shadow_report_record,
        ),
        *_pub_build_role_checks(
            role=role,
            shadow_report_record=shadow_report_record,
        ),
        *_pub_build_profile_checks(
            materialization_profile=materialization_profile,
            shadow_report_record=shadow_report_record,
            minimal_dq_record=minimal_dq_record,
        ),
    ]
    return tuple(checks)


def _pub_build_minimal_dq_check(
    minimal_dq_record: DerivedMinimalDQSummaryRecord | None,
) -> CertificationCheckResult:
    passed = minimal_dq_record is not None and minimal_dq_record.passed
    return CertificationCheckResult(
        name="minimal_dq_passed",
        severity=PublicationSafetySeverity.ERROR,
        passed=passed,
        message=(
            "minimal dq passed"
            if passed
            else "minimal dq missing or contains blocking errors"
        ),
        metric_value=0 if minimal_dq_record is None else minimal_dq_record.error_count,
        threshold_value=0,
    )


def _pub_build_manifest_check(
    manifest: CompatibilityManifest,
) -> CertificationCheckResult:
    passed = manifest.is_complete()
    return CertificationCheckResult(
        name="manifest_complete",
        severity=PublicationSafetySeverity.ERROR,
        passed=passed,
        message=("manifest complete" if passed else "manifest missing required fields"),
        metric_value=len(manifest.missing_required_fields()),
        threshold_value=0,
    )


def _pub_build_shadow_ready_gate_check(
    common_checks: tuple[CertificationCheckResult, ...],
) -> CertificationCheckResult:
    passed = all(
        check.passed or check.severity != PublicationSafetySeverity.ERROR
        for check in common_checks
    )
    return CertificationCheckResult(
        name="shadow_ready_passed",
        severity=PublicationSafetySeverity.ERROR,
        passed=passed,
        message=(
            "shadow_ready gate passed"
            if passed
            else "shadow_ready prerequisites are not satisfied"
        ),
        metric_value=0 if passed else 1,
        threshold_value=0,
    )


def _pub_build_diff_or_audit_checks(
    *,
    materialization_profile: MaterializationProfile,
    shadow_report_record: ShadowDiffReportRecord | None,
) -> tuple[CertificationCheckResult, ...]:
    if materialization_profile == MaterializationProfile.OFFLINE:
        return (_pub_build_sample_audit_check(shadow_report_record),)
    return (_pub_build_shadow_diff_check(shadow_report_record),)


def _pub_build_role_checks(
    *,
    role: DerivedRole,
    shadow_report_record: ShadowDiffReportRecord | None,
) -> tuple[CertificationCheckResult, ...]:
    if role == DerivedRole.FACTOR:
        return (_pub_build_factor_distribution_check(shadow_report_record),)
    if role == DerivedRole.FEATURE:
        return (_pub_build_feature_parity_check(shadow_report_record),)
    return ()


def _pub_build_profile_checks(
    *,
    materialization_profile: MaterializationProfile,
    shadow_report_record: ShadowDiffReportRecord | None,
    minimal_dq_record: DerivedMinimalDQSummaryRecord | None,
) -> tuple[CertificationCheckResult, ...]:
    if materialization_profile == MaterializationProfile.SERIES:
        return (_pub_build_series_shadow_parity_check(shadow_report_record),)
    if materialization_profile == MaterializationProfile.OFFLINE:
        return (_pub_build_offline_reproducibility_check(minimal_dq_record),)
    return ()


def _pub_build_shadow_diff_check(
    shadow_report_record: ShadowDiffReportRecord | None,
) -> CertificationCheckResult:
    passed = _pub_shadow_report_passed(shadow_report_record)
    return CertificationCheckResult(
        name="shadow_diff_passed",
        severity=PublicationSafetySeverity.ERROR,
        passed=passed,
        message=(
            "shadow compare passed"
            if passed
            else "shadow compare missing or contains blocking errors"
        ),
        metric_value=_pub_shadow_report_error_count(shadow_report_record),
        threshold_value=0,
    )


def _pub_build_sample_audit_check(
    shadow_report_record: ShadowDiffReportRecord | None,
) -> CertificationCheckResult:
    passed = _pub_shadow_report_passed(shadow_report_record)
    return CertificationCheckResult(
        name="sample_audit_passed",
        severity=PublicationSafetySeverity.ERROR,
        passed=passed,
        message=(
            "offline sample audit passed"
            if passed
            else "offline sample audit missing or contains blocking errors"
        ),
        metric_value=_pub_shadow_report_error_count(shadow_report_record),
        threshold_value=0,
    )


def _pub_build_factor_distribution_check(
    shadow_report_record: ShadowDiffReportRecord | None,
) -> CertificationCheckResult:
    sample_count = _pub_shadow_report_metric_int(shadow_report_record, "sample_count")
    passed = sample_count > 0
    return CertificationCheckResult(
        name="factor_distribution_stability",
        severity=PublicationSafetySeverity.ERROR,
        passed=passed,
        message=(
            "factor distribution audit has samples"
            if passed
            else "factor distribution audit is missing sample coverage"
        ),
        metric_value=sample_count,
        threshold_value=1,
    )


def _pub_build_feature_parity_check(
    shadow_report_record: ShadowDiffReportRecord | None,
) -> CertificationCheckResult:
    passed = _pub_shadow_report_passed(shadow_report_record)
    return CertificationCheckResult(
        name="feature_parity_ready",
        severity=PublicationSafetySeverity.ERROR,
        passed=passed,
        message=(
            "feature parity checks passed"
            if passed
            else "feature parity checks are missing or failed"
        ),
        metric_value=_pub_shadow_report_error_count(shadow_report_record),
        threshold_value=0,
    )


def _pub_build_series_shadow_parity_check(
    shadow_report_record: ShadowDiffReportRecord | None,
) -> CertificationCheckResult:
    passed = _pub_shadow_report_passed(shadow_report_record)
    return CertificationCheckResult(
        name="series_shadow_parity",
        severity=PublicationSafetySeverity.ERROR,
        passed=passed,
        message=(
            "series shadow parity passed"
            if passed
            else "series shadow parity is missing or failed"
        ),
        metric_value=_pub_shadow_report_error_count(shadow_report_record),
        threshold_value=0,
    )


def _pub_build_offline_reproducibility_check(
    minimal_dq_record: DerivedMinimalDQSummaryRecord | None,
) -> CertificationCheckResult:
    passed = minimal_dq_record is not None and minimal_dq_record.passed
    computable_value_count = 0
    if minimal_dq_record is not None:
        raw_value = minimal_dq_record.payload.get("computable_value_count", 0)
        if isinstance(raw_value, int):
            computable_value_count = raw_value
    return CertificationCheckResult(
        name="offline_dataset_reproducibility",
        severity=PublicationSafetySeverity.ERROR,
        passed=passed,
        message=(
            "offline dataset reproducibility checks passed"
            if passed
            else "offline dataset reproducibility checks failed"
        ),
        metric_value=computable_value_count,
        threshold_value=1,
    )


def _pub_shadow_report_passed(
    shadow_report_record: ShadowDiffReportRecord | None,
) -> bool:
    return shadow_report_record is not None and shadow_report_record.error_count == 0


def _pub_shadow_report_metric_int(
    shadow_report_record: ShadowDiffReportRecord | None,
    key: str,
) -> int:
    if shadow_report_record is None:
        return 0
    value = shadow_report_record.payload.get(key)
    return value if isinstance(value, int) else 0


def _pub_shadow_report_error_count(
    shadow_report_record: ShadowDiffReportRecord | None,
) -> int:
    if shadow_report_record is None:
        return 0
    return shadow_report_record.error_count


# ===========================================================================
# cascade_protocol.py
# ---------------------------------------------------------------------------
# Invalidation cascade protocol with BFS propagation and state machine.
#
# I-CASC-01: BFS multi-level propagation
# I-CASC-02: State machine (fresh -> stale -> recomputing -> healed)
# I-CASC-03: Cycle guard + micro-batch merge + max depth
# INVAL-IC-1: repair_batch failure resilience
# INVAL-IC-2: Dead letter queue
# INVAL-IC-3: Priority queue ordering
# INVAL-IC-4: Cross-event deduplication (subsumed healing)
# ===========================================================================


class CascadeStatus(StrEnum):
    """Cascade propagation lifecycle status."""

    FRESH = "fresh"
    STALE = "stale"
    RECOMPUTING = "recomputing"
    HEALED = "healed"
    DEAD_LETTER = "dead_letter"


class CascadeDepthExceededError(Exception):
    """Raised when cascade propagation exceeds the configured max depth."""

    def __init__(self, derived_id: str, depth: int) -> None:
        self.derived_id = derived_id
        self.depth = depth
        super().__init__(f"cascade depth exceeded for {derived_id}: depth={depth}")


REALTIME_CASCADE_MAX_DEPTH = 5
CASCADE_MAX_RETRY_COUNT = 3


@dataclass(frozen=True)
class RepairBatchResult:
    """Result of a repair batch operation containing successes and failures."""

    repaired: tuple[DerivedMaterializationResult, ...]
    failed: tuple[str, ...]


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

            # Skip source domain root refs (e.g. "market.stock_daily")
            # but still traverse downstream deps
            is_source_domain_root = depth == 0 and current_id.startswith(
                f"{event.source_domain}."
            )

            if not is_source_domain_root:
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
                    role="factor",
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
    ) -> RepairBatchResult:
        """
        Repair stale invalidations in priority/depth order.

        Transitions each record through: stale -> recomputing -> healed.
        On failure, increments retry count. If retry_count >= max, marks
        as dead letter; otherwise reverts to stale and continues to
        the next item. Never raises due to individual item failures.

        Returns:
            RepairBatchResult with successfully repaired items and failed IDs.

        """
        results: list[DerivedMaterializationResult] = []
        failed_ids: list[str] = []

        # Already sorted by role priority, depth, then created_at
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
                # Mark any subsumed stale records as healed
                self._mark_subsumed_healed(
                    healed_id=invalidation.invalidation_id,
                    derived_id=invalidation.derived_id,
                    version=invalidation.version,
                    affected_start=invalidation.affected_start,
                    affected_end=invalidation.affected_end,
                )
            except Exception as exc:
                error_message = str(exc)
                logger.error(
                    "repair failed for {}: {}",
                    invalidation.invalidation_id,
                    error_message,
                )
                new_retry_count = invalidation.retry_count + 1
                self._catalog_service.increment_retry_count(
                    invalidation.invalidation_id,
                )
                if new_retry_count >= CASCADE_MAX_RETRY_COUNT:
                    dead_letter_at = datetime.now(UTC).isoformat()
                    self._catalog_service.mark_invalidation_dead_letter(
                        invalidation.invalidation_id,
                        error_message,
                        dead_letter_at,
                    )
                    logger.warning(
                        "dead-lettered {} after {} retries",
                        invalidation.invalidation_id,
                        new_retry_count,
                    )
                else:
                    # State transition: recomputing -> stale (failure revert)
                    self._catalog_service.mark_invalidation_status(
                        invalidation.invalidation_id,
                        CascadeStatus.STALE,
                    )
                failed_ids.append(invalidation.invalidation_id)

        return RepairBatchResult(
            repaired=tuple(results),
            failed=tuple(failed_ids),
        )

    def _emit_depth_alert(self, derived_id: str, depth: int) -> None:
        """Log a warning when cascade depth is exceeded."""
        logger.warning(
            "cascade depth exceeded for {}: depth={} > max_depth={}",
            derived_id,
            depth,
            self._max_depth,
        )

    def _mark_subsumed_healed(
        self,
        healed_id: str,
        derived_id: str,
        version: int,
        affected_start: str,
        affected_end: str,
    ) -> None:
        """Mark stale records subsumed by a successful repair as healed."""
        stale_records = self._catalog_service.list_stale_by_derived_version(
            derived_id,
            version,
        )
        for record in stale_records:
            if (
                record.invalidation_id == healed_id
                or record.affected_start < affected_start
                or record.affected_end > affected_end
            ):
                continue
            self._catalog_service.mark_invalidation_status(
                record.invalidation_id,
                CascadeStatus.HEALED,
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
                merged[key] = replace(
                    existing,
                    affected_start=min(existing.affected_start, record.affected_start),
                    affected_end=max(existing.affected_end, record.affected_end),
                )
        return list(merged.values())


# ===========================================================================
# materialization_orchestrator.py
# ---------------------------------------------------------------------------
# Port-side unified derived materialization orchestration.
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
# runtime_input.py
# ---------------------------------------------------------------------------
# Runtime input provider backed by local truth-layer parquet and derived
# artifacts.
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

# Maps market dataset refs to MarketService method names.
_MARKET_SERVICE_METHODS: dict[str, str] = {
    "market.stock_daily": "get_stock_bars",
    "market.adj_factor": "get_adj_factors",
    "market.stock_status": "get_stock_status",
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
# factor_orthogonalization_service.py
# ---------------------------------------------------------------------------
# Factor orthogonalization service.
#
# Orchestrates loading factor artifacts and delegating to the Core
# orthogonalize() pure function.
# ===========================================================================


class FactorOrthogonalizationService:
    """
    Orthogonalize a target factor against control factors.

    Loads the target and control factor artifacts via
    :class:`DerivedArtifactReader`, joins them on
    ``(trade_date, instrument_id)``, and delegates to the pure-function
    :func:`~ditto_engine.engine.evaluation.metrics.orthogonalize` from
    ``ditto_engine``.
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
