"""
Certification rule builders for derived publication safety gates.

Extracted from ``publication_facade`` so the rule engine can evolve
independently of the facade orchestration logic.

All functions are pure (module-level) — no facade or service dependencies.
"""

from __future__ import annotations

from ditto_analytics.publication_safety import (
    CertificationCheckResult,
    CertificationStage,
    CompatibilityManifest,
    PublicationSafetySeverity,
)
from ditto_data.models.publication_safety import (
    DerivedMinimalDQSummaryRecord,
    ShadowDiffReportRecord,
)
from ditto_kernel.strategy import DerivedRole, MaterializationProfile

__all__ = ["build_certification_checks"]


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Internal rule builders
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Shadow-report helpers
# ---------------------------------------------------------------------------


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
