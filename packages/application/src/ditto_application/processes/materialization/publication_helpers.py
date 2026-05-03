"""Pure helpers for derived publication shadow diff, trace, and certification."""

from __future__ import annotations

from dataclasses import asdict
from typing import cast
from uuid import uuid4

import polars as pl
from ditto_features.publication_safety import (
    CertificationReport,
    CompatibilityManifest,
    ShadowDiffReport,
    ShadowTraceRecord,
)
from ditto_kernel.json_types import JsonDict, JsonValue
from ditto_kernel.publication_safety import (
    CompatibilityManifestRecord,
    ShadowDiffReportRecord,
    ShadowTraceRecordRecord,
)

from ditto_application.config import now_iso

_VALUE_DIFF_TOLERANCE = 1e-12


def _build_combined_frame(
    candidate_frame: pl.DataFrame,
    baseline_frame: pl.DataFrame,
) -> pl.DataFrame:
    """Prepare and join candidate/baseline frames into a single comparison frame."""
    candidate_prepared = _prepare_compare_frame(candidate_frame, "candidate")
    baseline_prepared = _prepare_compare_frame(baseline_frame, "baseline")
    return candidate_prepared.join(
        baseline_prepared,
        on=["instrument_id", "trade_date"],
        how="full",
        coalesce=True,
    ).sort(["instrument_id", "trade_date"])


def build_shadow_diff_report(
    *,
    derived_id: str,
    candidate_version: int,
    baseline_version: int,
    candidate_frame: pl.DataFrame,
    baseline_frame: pl.DataFrame,
    candidate_manifest_hash: str,
    baseline_manifest_hash: str,
) -> ShadowDiffReport:
    """Build a shadow diff report comparing candidate and baseline data frames."""
    combined = _build_combined_frame(candidate_frame, baseline_frame)
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


def build_shadow_traces(
    *,
    report: ShadowDiffReport,
    candidate_frame: pl.DataFrame,
    baseline_frame: pl.DataFrame,
) -> tuple[ShadowTraceRecord, ...]:
    """Build shadow trace records from the diff report and data frames."""
    combined = _build_combined_frame(candidate_frame, baseline_frame)
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


def to_shadow_report_record(report: ShadowDiffReport) -> ShadowDiffReportRecord:
    """Convert a domain ShadowDiffReport into a persistence record."""
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


def to_shadow_trace_record(
    derived_id: str,
    trace: ShadowTraceRecord,
) -> ShadowTraceRecordRecord:
    """Convert a domain ShadowTraceRecord into a persistence record."""
    return ShadowTraceRecordRecord(
        trace_id=trace.trace_id,
        report_id=trace.report_id,
        derived_id=derived_id,
        payload=cast(JsonDict, asdict(trace)),
        sampled_at=trace.sampled_at,
    )


def certification_payload(report: CertificationReport) -> JsonDict:
    """Serialize a CertificationReport into the JSON payload stored in persistence."""
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


def hydrate_manifest(record: CompatibilityManifestRecord) -> CompatibilityManifest:
    """Reconstruct a domain CompatibilityManifest from a persistence record."""
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
