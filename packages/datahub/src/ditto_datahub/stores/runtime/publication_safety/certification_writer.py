"""Writer for publication safety certification reports."""

from pathlib import Path

from ditto_datahub.models.publication_safety import CertificationReportRecord
from ditto_datahub.stores.runtime.publication_safety._json_records import (
    write_json_file,
)


class CertificationWriter:
    """File-based writer for certification reports."""

    def __init__(self, base_path: Path) -> None:
        self._base_path = (
            Path(base_path) / "derived" / "publication_safety" / "certification"
        )
        self._base_path.mkdir(parents=True, exist_ok=True)

    def write_report(self, record: CertificationReportRecord) -> None:
        """Persist a certification report record."""
        file_path = (
            self._base_path
            / record.derived_id
            / f"v{record.version}"
            / record.stage
            / f"{record.report_id}.json"
        )
        write_json_file(file_path, record.to_json_dict())
