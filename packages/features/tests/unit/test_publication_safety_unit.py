"""Tests for publication safety models."""

from ditto_features.publication_safety import (
    CertificationCheckResult,
    CertificationPack,
    CertificationReport,
    CertificationStage,
    CompatibilityManifest,
    PublicationSafetySeverity,
    ShadowDiffReport,
)
from ditto_kernel.strategy import DerivedRole, MaterializationProfile


class TestCompatibilityManifest:
    """Tests for CompatibilityManifest."""

    def test_manifest_reports_missing_required_fields(self) -> None:
        """Test manifest detects incomplete required fields."""
        manifest = CompatibilityManifest(
            engine_codegen_version=None,
            analysis_version="analysis-v1",
            polars_version="1.30.0",
            expr_serialization_format="expr-json-v1",
            operator_fingerprint="operator-fingerprint",
            global_compile_flags={"pushdown": True},
            calendar_id="cn_xshg",
            timezone="Asia/Shanghai",
            time_semantics_version="time-v1",
        )

        assert manifest.is_complete() is False
        assert manifest.missing_required_fields() == ("engine_codegen_version",)

    def test_manifest_complete_has_no_missing_fields(self) -> None:
        """Test complete manifest reports no missing required fields."""
        manifest = CompatibilityManifest(
            engine_codegen_version="codegen-v1",
            analysis_version="analysis-v1",
            polars_version="1.30.0",
            expr_serialization_format="expr-json-v1",
            operator_fingerprint="operator-fingerprint",
            global_compile_flags={"pushdown": True},
            calendar_id="cn_xshg",
            timezone="Asia/Shanghai",
            time_semantics_version="time-v1",
            manifest_hash="manifest-hash",
        )

        assert manifest.is_complete() is True
        assert manifest.missing_required_fields() == ()


class TestShadowDiffReport:
    """Tests for ShadowDiffReport."""

    def test_error_count_blocks_shadow_diff(self) -> None:
        """Test shadow diff with blocking errors is marked as failed."""
        report = ShadowDiffReport(
            report_id="diff-001",
            derived_id="factor.momentum_20d",
            candidate_version=3,
            baseline_version=2,
            request_count=200,
            sample_count=150,
            schema_match=True,
            value_diff_rate=0.01,
            coverage_delta=-0.005,
            freshness_delta=0.0,
            latency_p50_delta=0.1,
            latency_p95_delta=0.3,
            fallback_ratio_delta=0.0,
            error_count=1,
            warning_count=0,
            info_count=0,
            candidate_manifest_hash="manifest-candidate",
            baseline_manifest_hash="manifest-baseline",
            created_at="2026-03-13T12:00:00+08:00",
        )

        assert report.has_blocking_errors() is True


class TestCertificationReport:
    """Tests for CertificationReport."""

    def test_blocking_error_fails_certification(self) -> None:
        """Test certification report fails when an ERROR check fails."""
        report = CertificationReport(
            report_id="cert-001",
            pack=CertificationPack(
                pack_id="pack-factor-series",
                role=DerivedRole.FACTOR,
                materialization_profile=MaterializationProfile.SERIES,
                stage=CertificationStage.PUBLISH_READY,
                check_names=("distribution_stability", "shadow_parity"),
            ),
            derived_id="factor.momentum_20d",
            version=3,
            checks=(
                CertificationCheckResult(
                    name="distribution_stability",
                    severity=PublicationSafetySeverity.ERROR,
                    passed=False,
                    message="drift exceeds threshold",
                    metric_value=0.18,
                    threshold_value=0.10,
                ),
            ),
            manifest_hash="manifest-hash",
            shadow_diff_report_id="diff-001",
            created_at="2026-03-13T12:00:00+08:00",
        )

        assert report.has_blocking_errors() is True
        assert report.is_passed() is False

    def test_warning_only_does_not_block_certification(self) -> None:
        """Test warning checks remain publishable when no ERROR is present."""
        report = CertificationReport(
            report_id="cert-002",
            pack=CertificationPack(
                pack_id="pack-feature-state",
                role=DerivedRole.FEATURE,
                materialization_profile=MaterializationProfile.STATE,
                stage=CertificationStage.SHADOW_READY,
                check_names=("snapshot_consistency",),
            ),
            derived_id="feature.state_snapshot",
            version=5,
            checks=(
                CertificationCheckResult(
                    name="snapshot_consistency",
                    severity=PublicationSafetySeverity.WARNING,
                    passed=False,
                    message="lag is close to limit",
                    metric_value=8.0,
                    threshold_value=5.0,
                ),
            ),
            manifest_hash="manifest-hash",
            shadow_diff_report_id=None,
            created_at="2026-03-13T12:00:00+08:00",
        )

        assert report.has_blocking_errors() is False
        assert report.is_passed() is True
