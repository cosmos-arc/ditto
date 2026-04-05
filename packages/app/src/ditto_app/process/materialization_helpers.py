"""
Minimal DQ summary, manifest building, and dependency classification helpers.

Builds ``DerivedMinimalDQSummaryRecord`` from a materialized frame,
``CompatibilityManifestRecord`` for publication safety, and classifies
dependency references for durable persistence.
"""

from __future__ import annotations

import platform
from dataclasses import asdict, replace
from hashlib import sha256
from typing import cast

import orjson
import polars as pl
from ditto_analytics.materialization import CompileIdentity
from ditto_analytics.publication_safety import (
    CompatibilityManifest,
    DerivedMinimalDQSummary,
)
from ditto_data.models.publication_safety import (
    CompatibilityManifestRecord,
    DerivedMinimalDQSummaryRecord,
    JsonDict,
)
from ditto_data.services import DerivedCatalogService
from ditto_kernel.specs import DerivedSpec

from ditto_app.query._utils import now_iso

__all__ = [
    "build_manifest_record",
    "build_minimal_dq_record",
    "dependency_refs",
    "resolve_shadow_baseline",
]


# ===========================================================================
# DQ summary
# ===========================================================================


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
    Compute the fraction of jumps exceeding 3σ in consecutive value pct_changes.

    For each entity, compute pct_change between consecutive time-ordered rows.
    A "jump" is ``abs(pct_change) > 3 * pct_change_std`` (z-score logic).

    ``value_std`` is preserved for API compatibility but is not used in the
    threshold calculation — the threshold is derived from the pct_change
    distribution itself, ensuring correct scale matching.
    """
    _ = value_std

    time_keys = [col for col in frame.columns if col in ("trade_date", "date", "time")]
    entity_keys = [
        col for col in frame.columns if col in ("instrument_id", "entity_id", "code")
    ]

    if not time_keys or not entity_keys:
        return 0.0

    computable = frame.filter(
        pl.col("value").is_not_null() & pl.col("value").is_not_nan(),
    ).sort(entity_keys + time_keys)

    _MIN_PCT_CHANGE_OBS = 2
    if computable.height < _MIN_PCT_CHANGE_OBS:
        return 0.0

    pct_changes = computable.group_by(entity_keys[0], maintain_order=True).agg(
        pct=pl.col("value").pct_change(1).drop_nulls(),
    )

    if pct_changes.is_empty():
        return 0.0

    all_pct = pct_changes.select(pl.col("pct").explode())
    if all_pct.is_empty():
        return 0.0

    all_pct_values = all_pct.to_series()
    pct_std_raw = all_pct_values.std()
    if pct_std_raw is None or not isinstance(pct_std_raw, float) or pct_std_raw <= 0:
        return 0.0

    threshold = 3.0 * pct_std_raw
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
# Manifest building
# ===========================================================================


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


# ===========================================================================
# Shadow baseline
# ===========================================================================


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


# ===========================================================================
# Dependency reference classification
# ===========================================================================


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
