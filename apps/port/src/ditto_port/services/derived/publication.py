"""Port facade for derived publication orchestration."""

from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime
from typing import cast
from uuid import uuid4

import polars as pl
from ditto_core.engine.materialization.models import (
    DerivedRunStatus,
    DerivedVersionStatus,
)
from ditto_core.engine.publication_safety import (
    CertificationPack,
    CertificationReport,
    CertificationStage,
    CompatibilityManifest,
    ShadowDiffReport,
    ShadowTraceRecord,
)
from ditto_core.engine.specs import DerivedRole, MaterializationProfile
from ditto_datahub.models.derived import DerivedSpecRecord, DerivedVersionRecord
from ditto_datahub.models.publication_safety import (
    CertificationReportRecord,
    CompatibilityManifestRecord,
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
from ditto_datahub.services.derived_shadow_slot_service import DerivedShadowSlotService

from ditto_port.services.derived.publication_rules import build_certification_checks

__all__ = ["DerivedPublicationFacade"]

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
            activated_at=_now_iso(),
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
            raise ValueError(f"shadow baseline not found for derived_id={derived_id}")
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
        checks = build_certification_checks(
            stage=stage,
            role=DerivedRole(spec_record.role),
            materialization_profile=MaterializationProfile(
                spec_record.materialization_profile
            ),
            manifest=manifest,
            minimal_dq_record=minimal_dq_record,
            shadow_report_record=shadow_report_record,
        )
        pack = CertificationPack(
            pack_id=(
                f"pack-{spec_record.role.lower()}"
                f"-{spec_record.materialization_profile.lower()}"
                f"-{stage.value}"
            ),
            role=DerivedRole(spec_record.role),
            materialization_profile=MaterializationProfile(
                spec_record.materialization_profile
            ),
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
            created_at=_now_iso(),
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
        promoted_at = _now_iso()
        self._move_primary_pointer(
            derived_id=derived_id,
            target_version=candidate_version,
            target_status=DerivedVersionStatus.PUBLISHED,
            updated_at=promoted_at,
        )
        self._shadow_slot_service.disable_slot(derived_id, promoted_at)
        promoted = self._catalog_service.get_version(derived_id, candidate_version)
        if promoted is None:
            raise KeyError(
                "promoted version not found for "
                + f"derived_id={derived_id} version={candidate_version}"
            )
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
            raise ValueError(
                "rollback target must already be published for "
                + f"derived_id={derived_id} version={target_version}"
            )
        rolled_back_at = _now_iso()
        self._move_primary_pointer(
            derived_id=derived_id,
            target_version=target_version,
            target_status=target.status,
            updated_at=rolled_back_at,
        )
        rolled_back = self._catalog_service.get_version(derived_id, target_version)
        if rolled_back is None:
            raise KeyError(
                "rollback target not found for "
                + f"derived_id={derived_id} version={target_version}"
            )
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
            raise ValueError(
                "only published versions can be deprecated for "
                + f"derived_id={derived_id} version={version}"
            )
        if version_record.is_primary:
            raise ValueError(
                "primary published version must be rolled back before deprecate for "
                + f"derived_id={derived_id} version={version}"
            )
        deprecated_at = _now_iso()
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
            raise KeyError(
                "deprecated version not found for "
                + f"derived_id={derived_id} version={version}"
            )
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
                raise ValueError(
                    f"active shadow slot not found for derived_id={derived_id}"
                )
            return slot
        if candidate_version is None:
            raise ValueError(
                "candidate_version is required when baseline_version is set"
            )
        self._require_version(derived_id, candidate_version)
        if baseline_version is not None:
            self._require_version(derived_id, baseline_version)
        return DerivedShadowSlotRecord(
            derived_id=derived_id,
            candidate_version=candidate_version,
            baseline_version=baseline_version,
            activated_at=_now_iso(),
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
            raise ValueError(
                "candidate version is not materialized successfully for "
                + f"derived_id={derived_id} version={candidate_version}"
            )
        manifest_record = self._require_manifest(
            derived_id=derived_id,
            version=candidate_version,
        )
        manifest = _hydrate_manifest(manifest_record)
        if not manifest.is_complete():
            raise ValueError(
                "candidate manifest is incomplete for "
                + f"derived_id={derived_id} version={candidate_version}"
            )
        slot = self._shadow_slot_service.get_active_slot(derived_id)
        if slot is None or slot.candidate_version != candidate_version:
            raise ValueError(
                "active shadow slot missing for "
                + f"derived_id={derived_id} version={candidate_version}"
            )
        if slot.baseline_version is None:
            raise ValueError(f"shadow baseline missing for derived_id={derived_id}")
        shadow_report = self._publication_record_service.get_latest_shadow_report(
            derived_id,
            candidate_version,
            slot.baseline_version,
        )
        if shadow_report is None or shadow_report.error_count > 0:
            raise ValueError(
                "latest shadow compare is not publishable for "
                + f"derived_id={derived_id} version={candidate_version}"
            )
        certification = (
            self._publication_record_service.get_latest_certification_report(
                derived_id,
                candidate_version,
                CertificationStage.PUBLISH_READY.value,
            )
        )
        if certification is None or certification.payload.get("passed") is not True:
            raise ValueError(
                "publish_ready gate has not passed for "
                + f"derived_id={derived_id} version={candidate_version}"
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
            raise KeyError(
                "derived spec not found for "
                + f"derived_id={derived_id} version={version}"
            )
        return spec_record

    def _require_version(self, derived_id: str, version: int) -> DerivedVersionRecord:
        version_record = self._catalog_service.get_version(derived_id, version)
        if version_record is None:
            raise KeyError(
                "derived version not found for "
                + f"derived_id={derived_id} version={version}"
            )
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
            raise KeyError(
                "compatibility manifest not found for "
                + f"derived_id={derived_id} version={version}"
            )
        return manifest_record


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
    error_count = 0
    if not schema_match:
        error_count += 1
    if diff_count > 0:
        error_count += 1
    if candidate_frame.height != baseline_frame.height:
        error_count += 1
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
        created_at=_now_iso(),
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
        if isinstance(item, bool | int | float | str):
            compile_flags[key] = item
            continue
        raise TypeError("global_compile_flags values must be primitive JSON values")
    return compile_flags


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()
