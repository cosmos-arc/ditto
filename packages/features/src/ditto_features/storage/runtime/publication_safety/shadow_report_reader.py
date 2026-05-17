"""Reader for publication safety shadow reports."""

from pathlib import Path

from ditto_features.publication_safety_records import (
    ShadowDiffReportRecord,
    ShadowTraceRecordRecord,
)
from ditto_features.storage.runtime.publication_safety._json_records import (
    list_json_files,
    read_json_file,
)


class ShadowReportReader:
    """File-based reader for shadow diff and trace records."""

    def __init__(self, base_path: Path) -> None:
        root = Path(base_path) / "derived" / "publication_safety"
        self._diff_base = root / "shadow_diff"
        self._trace_base = root / "shadow_trace"

    def read_report(
        self,
        derived_id: str,
        report_id: str,
    ) -> ShadowDiffReportRecord | None:
        """Read a shadow diff report by derived/report id."""
        derived_root = self._diff_base / derived_id
        if not derived_root.exists():
            return None

        matches = sorted(derived_root.rglob(f"{report_id}.json"))
        if not matches:
            return None

        payload = read_json_file(matches[0])
        if payload is None:
            return None
        return ShadowDiffReportRecord.from_json_dict(payload)

    def list_trace_records(
        self,
        derived_id: str,
        report_id: str,
    ) -> list[ShadowTraceRecordRecord]:
        """List trace records for a shadow diff report."""
        trace_dir = self._trace_base / derived_id / report_id
        records: list[ShadowTraceRecordRecord] = []
        for file_path in list_json_files(trace_dir):
            payload = read_json_file(file_path)
            if payload is None:
                continue
            records.append(ShadowTraceRecordRecord.from_json_dict(payload))
        return sorted(records, key=lambda record: (record.sampled_at, record.trace_id))

    def get_latest_report(
        self,
        derived_id: str,
        candidate_version: int,
        baseline_version: int,
    ) -> ShadowDiffReportRecord | None:
        """Return the latest shadow diff report for a candidate/baseline pair."""
        report_dir = (
            self._diff_base
            / derived_id
            / f"candidate=v{candidate_version}"
            / f"baseline=v{baseline_version}"
        )
        reports: list[ShadowDiffReportRecord] = []
        for file_path in list_json_files(report_dir):
            payload = read_json_file(file_path)
            if payload is None:
                continue
            reports.append(ShadowDiffReportRecord.from_json_dict(payload))

        if not reports:
            return None
        return max(reports, key=lambda record: (record.created_at, record.report_id))
