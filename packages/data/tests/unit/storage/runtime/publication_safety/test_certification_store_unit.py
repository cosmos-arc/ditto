"""Tests for publication safety certification stores."""

from pathlib import Path

from ditto_data.models.publication_safety import CertificationReportRecord
from ditto_data.storage.runtime.publication_safety import (
    CertificationReader,
    CertificationWriter,
)


class TestCertificationStore:
    """Tests for certification reader/writer."""

    def test_certification_roundtrip(self, tmp_path: Path) -> None:
        """Test certification report can be written and read by identifiers."""
        writer = CertificationWriter(base_path=tmp_path)
        reader = CertificationReader(base_path=tmp_path)
        record = CertificationReportRecord(
            report_id="cert-001",
            derived_id="factor.momentum_20d",
            version=3,
            stage="publish_ready",
            pack_id="pack-factor-series",
            manifest_hash="manifest-hash-v3",
            payload={"error_count": 0, "warning_count": 1},
            created_at="2026-03-13T12:00:00+08:00",
        )

        writer.write_report(record)
        loaded = reader.read_report(
            "factor.momentum_20d",
            3,
            "publish_ready",
            "cert-001",
        )

        assert loaded == record

    def test_latest_certification_report_uses_newest_created_at(
        self, tmp_path: Path
    ) -> None:
        """Test latest certification report is selected by created_at."""
        writer = CertificationWriter(base_path=tmp_path)
        reader = CertificationReader(base_path=tmp_path)
        older = CertificationReportRecord(
            report_id="cert-older",
            derived_id="factor.momentum_20d",
            version=3,
            stage="publish_ready",
            pack_id="pack-factor-series",
            manifest_hash="manifest-hash-v3",
            payload={"error_count": 1},
            created_at="2026-03-13T12:00:00+08:00",
        )
        newer = CertificationReportRecord(
            report_id="cert-newer",
            derived_id="factor.momentum_20d",
            version=3,
            stage="publish_ready",
            pack_id="pack-factor-series",
            manifest_hash="manifest-hash-v3",
            payload={"error_count": 0},
            created_at="2026-03-13T12:10:00+08:00",
        )

        writer.write_report(older)
        writer.write_report(newer)

        latest = reader.get_latest_report("factor.momentum_20d", 3, "publish_ready")

        assert latest == newer
