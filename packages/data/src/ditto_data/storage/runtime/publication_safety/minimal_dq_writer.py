"""Writer for publication safety minimal DQ summaries."""

from pathlib import Path

from ditto_kernel.publication_safety import DerivedMinimalDQSummaryRecord

from ditto_data.storage.runtime.publication_safety._json_records import (
    write_json_file,
)


class MinimalDQWriter:
    """File-based writer for derived minimal DQ summaries."""

    def __init__(self, base_path: Path) -> None:
        self._base_path = (
            Path(base_path) / "derived" / "publication_safety" / "minimal_dq"
        )
        self._base_path.mkdir(parents=True, exist_ok=True)

    def write_summary(self, record: DerivedMinimalDQSummaryRecord) -> None:
        """Persist one minimal DQ summary record."""
        file_path = (
            self._base_path
            / record.derived_id
            / f"v{record.version}"
            / f"{record.run_id}.json"
        )
        write_json_file(file_path, record.to_json_dict())
