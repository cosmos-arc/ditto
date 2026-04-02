"""Reader for publication safety certification reports."""

from pathlib import Path

from ditto_data.models.publication_safety import CertificationReportRecord
from ditto_data.stores.runtime.publication_safety._json_records import (
    list_json_files,
    read_json_file,
)


class CertificationReader:
    """File-based reader for certification reports."""

    def __init__(self, base_path: Path) -> None:
        self._base_path = (
            Path(base_path) / "derived" / "publication_safety" / "certification"
        )

    def read_report(
        self,
        derived_id: str,
        version: int,
        stage: str,
        report_id: str,
    ) -> CertificationReportRecord | None:
        """Read a certification report by derived/version/stage/report."""
        file_path = (
            self._base_path / derived_id / f"v{version}" / stage / f"{report_id}.json"
        )
        payload = read_json_file(file_path)
        if payload is None:
            return None
        return CertificationReportRecord.from_json_dict(payload)

    def get_latest_report(
        self,
        derived_id: str,
        version: int,
        stage: str,
    ) -> CertificationReportRecord | None:
        """Return the latest certification report for a version/stage."""
        report_dir = self._base_path / derived_id / f"v{version}" / stage
        reports: list[CertificationReportRecord] = []
        for file_path in list_json_files(report_dir):
            payload = read_json_file(file_path)
            if payload is None:
                continue
            reports.append(CertificationReportRecord.from_json_dict(payload))

        if not reports:
            return None
        return max(reports, key=lambda record: (record.created_at, record.report_id))
