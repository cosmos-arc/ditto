"""Writer for publication safety shadow reports."""

from pathlib import Path

from ditto_kernel.publication_safety import (
    ShadowDiffReportRecord,
    ShadowTraceRecordRecord,
)

from ditto_features.storage.runtime.publication_safety._json_records import (
    write_json_file,
)


class ShadowReportWriter:
    """File-based writer for shadow diff and trace records."""

    def __init__(self, base_path: Path) -> None:
        root = Path(base_path) / "derived" / "publication_safety"
        self._diff_base = root / "shadow_diff"
        self._trace_base = root / "shadow_trace"
        self._diff_base.mkdir(parents=True, exist_ok=True)
        self._trace_base.mkdir(parents=True, exist_ok=True)

    def write_report(
        self,
        report: ShadowDiffReportRecord,
        traces: tuple[ShadowTraceRecordRecord, ...],
    ) -> None:
        """Persist a shadow diff report and its trace records."""
        report_path = (
            self._diff_base
            / report.derived_id
            / f"candidate=v{report.candidate_version}"
            / f"baseline=v{report.baseline_version}"
            / f"{report.report_id}.json"
        )
        write_json_file(report_path, report.to_json_dict())

        trace_dir = self._trace_base / report.derived_id / report.report_id
        for trace in traces:
            trace_path = trace_dir / f"{trace.trace_id}.json"
            write_json_file(trace_path, trace.to_json_dict())
