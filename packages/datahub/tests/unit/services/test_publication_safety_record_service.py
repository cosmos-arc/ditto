"""Tests for PublicationSafetyRecordService."""

from ditto_datahub.models.publication_safety import (
    CertificationReportRecord,
    CompatibilityManifestRecord,
    DerivedMinimalDQSummaryRecord,
    ShadowDiffReportRecord,
    ShadowTraceRecordRecord,
)
from ditto_datahub.services.publication_safety_record_service import (
    PublicationSafetyRecordService,
    PublicationSafetyRuntimeStores,
)
from pytest_mock import MockerFixture


def _stores(
    mocker: MockerFixture,
    **overrides: object,
) -> PublicationSafetyRuntimeStores:
    return PublicationSafetyRuntimeStores(
        manifest_reader=overrides.get("manifest_reader", mocker.Mock()),
        manifest_writer=overrides.get("manifest_writer", mocker.Mock()),
        minimal_dq_reader=overrides.get("minimal_dq_reader", mocker.Mock()),
        minimal_dq_writer=overrides.get("minimal_dq_writer", mocker.Mock()),
        shadow_report_reader=overrides.get("shadow_report_reader", mocker.Mock()),
        shadow_report_writer=overrides.get("shadow_report_writer", mocker.Mock()),
        certification_reader=overrides.get("certification_reader", mocker.Mock()),
        certification_writer=overrides.get("certification_writer", mocker.Mock()),
    )


class TestPublicationSafetyRecordService:
    """Tests for PublicationSafetyRecordService."""

    def test_save_manifest_delegates_to_writer(self, mocker: MockerFixture) -> None:
        """Test save_manifest() delegates to manifest writer."""
        manifest = CompatibilityManifestRecord(
            derived_id="factor.momentum_20d",
            version=3,
            manifest_hash="manifest-hash-v3",
            payload={"engine_codegen_version": "codegen-v1"},
            created_at="2026-03-13T12:00:00+08:00",
        )
        manifest_writer = mocker.Mock()
        service = PublicationSafetyRecordService(
            _stores(mocker, manifest_writer=manifest_writer)
        )

        service.save_manifest(manifest)

        manifest_writer.write_manifest.assert_called_once_with(manifest)

    def test_get_manifest_delegates_to_reader(self, mocker: MockerFixture) -> None:
        """Test get_manifest() delegates to manifest reader."""
        manifest = CompatibilityManifestRecord(
            derived_id="factor.momentum_20d",
            version=3,
            manifest_hash="manifest-hash-v3",
            payload={"engine_codegen_version": "codegen-v1"},
            created_at="2026-03-13T12:00:00+08:00",
        )
        manifest_reader = mocker.Mock()
        manifest_reader.read_manifest = mocker.Mock(return_value=manifest)
        service = PublicationSafetyRecordService(
            _stores(mocker, manifest_reader=manifest_reader)
        )

        result = service.get_manifest("factor.momentum_20d", 3)

        assert result == manifest
        manifest_reader.read_manifest.assert_called_once_with("factor.momentum_20d", 3)

    def test_save_shadow_report_delegates_to_writer(
        self, mocker: MockerFixture
    ) -> None:
        """Test save_shadow_report() delegates to shadow writer."""
        report = ShadowDiffReportRecord(
            report_id="diff-001",
            derived_id="factor.momentum_20d",
            candidate_version=3,
            baseline_version=2,
            error_count=0,
            warning_count=1,
            info_count=0,
            payload={"value_diff_rate": 0.01},
            created_at="2026-03-13T12:00:00+08:00",
        )
        traces = (
            ShadowTraceRecordRecord(
                trace_id="trace-001",
                report_id="diff-001",
                derived_id="factor.momentum_20d",
                payload={"instrument_id": 1},
                sampled_at="2026-03-13T12:01:00+08:00",
            ),
        )
        shadow_writer = mocker.Mock()
        service = PublicationSafetyRecordService(
            _stores(mocker, shadow_report_writer=shadow_writer)
        )

        service.save_shadow_report(report, traces)

        shadow_writer.write_report.assert_called_once_with(report, traces)

    def test_get_latest_shadow_report_delegates_to_reader(
        self, mocker: MockerFixture
    ) -> None:
        """Test latest shadow report lookup delegates to reader."""
        report = ShadowDiffReportRecord(
            report_id="diff-001",
            derived_id="factor.momentum_20d",
            candidate_version=3,
            baseline_version=2,
            error_count=0,
            warning_count=0,
            info_count=0,
            payload={"value_diff_rate": 0.01},
            created_at="2026-03-13T12:00:00+08:00",
        )
        shadow_reader = mocker.Mock()
        shadow_reader.get_latest_report = mocker.Mock(return_value=report)
        service = PublicationSafetyRecordService(
            _stores(mocker, shadow_report_reader=shadow_reader)
        )

        result = service.get_latest_shadow_report("factor.momentum_20d", 3, 2)

        assert result == report
        shadow_reader.get_latest_report.assert_called_once_with(
            "factor.momentum_20d", 3, 2
        )

    def test_save_certification_report_delegates_to_writer(
        self, mocker: MockerFixture
    ) -> None:
        """Test save_certification_report() delegates to certification writer."""
        record = CertificationReportRecord(
            report_id="cert-001",
            derived_id="factor.momentum_20d",
            version=3,
            stage="publish_ready",
            pack_id="pack-factor-series",
            manifest_hash="manifest-hash-v3",
            payload={"error_count": 0},
            created_at="2026-03-13T12:00:00+08:00",
        )
        certification_writer = mocker.Mock()
        service = PublicationSafetyRecordService(
            _stores(mocker, certification_writer=certification_writer)
        )

        service.save_certification_report(record)

        certification_writer.write_report.assert_called_once_with(record)

    def test_get_latest_certification_report_delegates_to_reader(
        self, mocker: MockerFixture
    ) -> None:
        """Test latest certification lookup delegates to reader."""
        record = CertificationReportRecord(
            report_id="cert-001",
            derived_id="factor.momentum_20d",
            version=3,
            stage="publish_ready",
            pack_id="pack-factor-series",
            manifest_hash="manifest-hash-v3",
            payload={"error_count": 0},
            created_at="2026-03-13T12:00:00+08:00",
        )
        certification_reader = mocker.Mock()
        certification_reader.get_latest_report = mocker.Mock(return_value=record)
        service = PublicationSafetyRecordService(
            _stores(mocker, certification_reader=certification_reader)
        )

        result = service.get_latest_certification_report(
            "factor.momentum_20d", 3, "publish_ready"
        )

        assert result == record
        certification_reader.get_latest_report.assert_called_once_with(
            "factor.momentum_20d", 3, "publish_ready"
        )

    def test_save_minimal_dq_summary_delegates_to_writer(
        self,
        mocker: MockerFixture,
    ) -> None:
        """Test save_minimal_dq_summary() delegates to minimal DQ writer."""
        record = DerivedMinimalDQSummaryRecord(
            derived_id="factor.momentum_20d",
            version=3,
            run_id="drv-001",
            passed=True,
            error_count=0,
            payload={"failed_checks": []},
            created_at="2026-03-14T12:00:00+08:00",
        )
        minimal_dq_writer = mocker.Mock()
        service = PublicationSafetyRecordService(
            _stores(mocker, minimal_dq_writer=minimal_dq_writer)
        )

        service.save_minimal_dq_summary(record)

        minimal_dq_writer.write_summary.assert_called_once_with(record)

    def test_get_latest_minimal_dq_summary_delegates_to_reader(
        self,
        mocker: MockerFixture,
    ) -> None:
        """Test latest minimal DQ lookup delegates to reader."""
        record = DerivedMinimalDQSummaryRecord(
            derived_id="factor.momentum_20d",
            version=3,
            run_id="drv-001",
            passed=False,
            error_count=1,
            payload={"failed_checks": ["value_has_no_nan"]},
            created_at="2026-03-14T12:00:00+08:00",
        )
        minimal_dq_reader = mocker.Mock()
        minimal_dq_reader.get_latest_summary = mocker.Mock(return_value=record)
        service = PublicationSafetyRecordService(
            _stores(mocker, minimal_dq_reader=minimal_dq_reader)
        )

        result = service.get_latest_minimal_dq_summary("factor.momentum_20d", 3)

        assert result == record
        minimal_dq_reader.get_latest_summary.assert_called_once_with(
            "factor.momentum_20d",
            3,
        )
