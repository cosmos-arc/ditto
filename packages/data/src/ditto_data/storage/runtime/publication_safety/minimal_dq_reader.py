"""Reader for publication safety minimal DQ summaries."""

from pathlib import Path

from ditto_data.models.publication_safety import DerivedMinimalDQSummaryRecord
from ditto_data.storage.runtime.publication_safety._json_records import (
    list_json_files,
    read_json_file,
)


class MinimalDQReader:
    """File-based reader for derived minimal DQ summaries."""

    def __init__(self, base_path: Path) -> None:
        self._base_path = (
            Path(base_path) / "derived" / "publication_safety" / "minimal_dq"
        )

    def read_summary(
        self,
        derived_id: str,
        version: int,
        run_id: str,
    ) -> DerivedMinimalDQSummaryRecord | None:
        """Read one minimal DQ summary by derived/version/run."""
        file_path = self._base_path / derived_id / f"v{version}" / f"{run_id}.json"
        payload = read_json_file(file_path)
        if payload is None:
            return None
        return DerivedMinimalDQSummaryRecord.from_json_dict(payload)

    def get_latest_summary(
        self,
        derived_id: str,
        version: int,
    ) -> DerivedMinimalDQSummaryRecord | None:
        """Return the latest minimal DQ summary for one derived version."""
        summary_root = self._base_path / derived_id / f"v{version}"
        records = [
            DerivedMinimalDQSummaryRecord.from_json_dict(payload)
            for path in list_json_files(summary_root)
            if (payload := read_json_file(path)) is not None
        ]
        if not records:
            return None
        return max(records, key=lambda record: record.created_at)
