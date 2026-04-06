"""
App facade for derived publication orchestration.

Provides ``DerivedPublicationFacade`` for the publication lifecycle
(shadow publish, compare, certify, promote, rollback, deprecate) and
the ``build_certification_checks`` rule builder.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import cast
from uuid import uuid4

import polars as pl
from ditto_analytics.materialization import DerivedRunStatus, DerivedVersionStatus
from ditto_analytics.publication_safety import (
    CertificationCheckResult,
    CertificationPack,
    CertificationReport,
    CertificationStage,
    CompatibilityManifest,
    PublicationSafetySeverity,
    ShadowDiffReport,
    ShadowTraceRecord,
)
from ditto_data.errors import DerivedNotFoundError, DerivedValidationError
from ditto_data.models.derived import (
    DerivedSpecRecord,
    DerivedVersionRecord,
)
from ditto_data.models.publication_safety import (
    CertificationReportRecord,
    CompatibilityManifestRecord,
    DerivedMinimalDQSummaryRecord,
    DerivedShadowSlotRecord,
    JsonDict,
    JsonValue,
    ShadowDiffReportRecord,
    ShadowTraceRecordRecord,
)
from ditto_data.services import (
    DerivedArtifactReader,
    DerivedCatalogService,
    PublicationSafetyRecordService,
)
from ditto_data.services.derived_shadow_slot_service import DerivedShadowSlotService
from ditto_kernel.specs import DerivedRole, MaterializationProfile

from ditto_app.query._utils import now_iso

__all__ = [
    "DerivedPublicationFacade",
    "build_certification_checks",
]


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
        stage: str | CertificationStage,
    ) -> CertificationReport:
        """Run one certification gate for a candidate version."""
        if not isinstance(stage, CertificationStage):
            stage = CertificationStage(stage)
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

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

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


# ===========================================================================
# Internal helpers (shadow diff / trace / certification)
# ===========================================================================


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
# Certification rule builders
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
