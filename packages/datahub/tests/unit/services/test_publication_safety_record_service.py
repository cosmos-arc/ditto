"""Tests for PublicationSafetyRecordService."""

from ditto_datahub.models.publication_safety import (
    CertificationReportRecord,
    CompatibilityManifestRecord,
    ShadowDiffReportRecord,
    ShadowTraceRecordRecord,
)
from ditto_datahub.services.publication_safety_record_service import (
    PublicationSafetyRecordService,
)
from pytest_mock import MockerFixture


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
            manifest_reader=mocker.Mock(),
            manifest_writer=manifest_writer,
            shadow_report_reader=mocker.Mock(),
            shadow_report_writer=mocker.Mock(),
            certification_reader=mocker.Mock(),
            certification_writer=mocker.Mock(),
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
            manifest_reader=manifest_reader,
            manifest_writer=mocker.Mock(),
            shadow_report_reader=mocker.Mock(),
            shadow_report_writer=mocker.Mock(),
            certification_reader=mocker.Mock(),
            certification_writer=mocker.Mock(),
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
            manifest_reader=mocker.Mock(),
            manifest_writer=mocker.Mock(),
            shadow_report_reader=mocker.Mock(),
            shadow_report_writer=shadow_writer,
            certification_reader=mocker.Mock(),
            certification_writer=mocker.Mock(),
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
            manifest_reader=mocker.Mock(),
            manifest_writer=mocker.Mock(),
            shadow_report_reader=shadow_reader,
            shadow_report_writer=mocker.Mock(),
            certification_reader=mocker.Mock(),
            certification_writer=mocker.Mock(),
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
            manifest_reader=mocker.Mock(),
            manifest_writer=mocker.Mock(),
            shadow_report_reader=mocker.Mock(),
            shadow_report_writer=mocker.Mock(),
            certification_reader=mocker.Mock(),
            certification_writer=certification_writer,
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
            manifest_reader=mocker.Mock(),
            manifest_writer=mocker.Mock(),
            shadow_report_reader=mocker.Mock(),
            shadow_report_writer=mocker.Mock(),
            certification_reader=certification_reader,
            certification_writer=mocker.Mock(),
        )

        result = service.get_latest_certification_report(
            "factor.momentum_20d", 3, "publish_ready"
        )

        assert result == record
        certification_reader.get_latest_report.assert_called_once_with(
            "factor.momentum_20d", 3, "publish_ready"
        )
