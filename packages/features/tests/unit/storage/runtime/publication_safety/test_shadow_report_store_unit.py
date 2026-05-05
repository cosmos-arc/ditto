"""Tests for publication safety shadow report stores."""

from pathlib import Path

from ditto_features.storage.runtime.publication_safety import (
    ShadowReportReader,
    ShadowReportWriter,
)
from ditto_kernel.publication_safety import (
    ShadowDiffReportRecord,
    ShadowTraceRecordRecord,
)


class TestShadowReportStore:
    """Tests for shadow diff and trace stores."""

    def test_shadow_report_and_trace_roundtrip(self, tmp_path: Path) -> None:
        """Test writer persists diff report and trace records together."""
        writer = ShadowReportWriter(base_path=tmp_path)
        reader = ShadowReportReader(base_path=tmp_path)
        report = ShadowDiffReportRecord(
            report_id="diff-001",
            derived_id="factor.momentum_20d",
            candidate_version=3,
            baseline_version=2,
            error_count=0,
            warning_count=1,
            info_count=0,
            payload={"value_diff_rate": 0.01, "schema_match": True},
            created_at="2026-03-13T12:00:00+08:00",
        )
        traces = (
            ShadowTraceRecordRecord(
                trace_id="trace-001",
                report_id="diff-001",
                derived_id="factor.momentum_20d",
                payload={"instrument_id": 1, "diff_category": "value_mismatch"},
                sampled_at="2026-03-13T12:01:00+08:00",
            ),
            ShadowTraceRecordRecord(
                trace_id="trace-002",
                report_id="diff-001",
                derived_id="factor.momentum_20d",
                payload={"instrument_id": 2, "diff_category": "coverage_drop"},
                sampled_at="2026-03-13T12:02:00+08:00",
            ),
        )

        writer.write_report(report, traces)

        assert reader.read_report("factor.momentum_20d", "diff-001") == report
        assert reader.list_trace_records("factor.momentum_20d", "diff-001") == list(
            traces
        )

    def test_latest_shadow_report_uses_newest_created_at(self, tmp_path: Path) -> None:
        """Test reader returns newest report for a candidate/baseline pair."""
        writer = ShadowReportWriter(base_path=tmp_path)
        reader = ShadowReportReader(base_path=tmp_path)
        older = ShadowDiffReportRecord(
            report_id="diff-older",
            derived_id="factor.momentum_20d",
            candidate_version=3,
            baseline_version=2,
            error_count=0,
            warning_count=0,
            info_count=0,
            payload={"value_diff_rate": 0.02},
            created_at="2026-03-13T12:00:00+08:00",
        )
        newer = ShadowDiffReportRecord(
            report_id="diff-newer",
            derived_id="factor.momentum_20d",
            candidate_version=3,
            baseline_version=2,
            error_count=0,
            warning_count=0,
            info_count=1,
            payload={"value_diff_rate": 0.01},
            created_at="2026-03-13T12:05:00+08:00",
        )

        writer.write_report(older, ())
        writer.write_report(newer, ())

        latest = reader.get_latest_report("factor.momentum_20d", 3, 2)

        assert latest == newer
