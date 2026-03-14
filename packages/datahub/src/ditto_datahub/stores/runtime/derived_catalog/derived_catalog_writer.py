"""Writer for derived catalog runtime metadata."""

from __future__ import annotations

from pathlib import Path

from ditto_datahub.models.derived import (
    DerivedPartitionRecord,
    DerivedRunRecord,
    DerivedSpecRecord,
    DerivedStateRecord,
    DerivedVersionRecord,
)
from ditto_datahub.stores.runtime.derived_catalog._json_records import write_json_file


class DerivedCatalogWriter:
    """File-based writer for derived catalog runtime metadata."""

    def __init__(self, base_path: Path) -> None:
        root = Path(base_path) / "derived" / "catalog"
        self._spec_base = root / "specs"
        self._version_base = root / "versions"
        self._state_base = root / "state"
        self._run_base = root / "runs"
        self._partition_base = root / "partitions"
        root.mkdir(parents=True, exist_ok=True)

    def write_spec(self, record: DerivedSpecRecord) -> None:
        """Persist spec metadata."""
        write_json_file(
            self._spec_base / record.derived_id / f"v{record.version}.json",
            record.to_json_dict(),
        )

    def write_version(self, record: DerivedVersionRecord) -> None:
        """Persist version metadata."""
        write_json_file(
            self._version_base / record.derived_id / f"v{record.version}.json",
            record.to_json_dict(),
        )

    def write_run(self, record: DerivedRunRecord) -> None:
        """Persist run metadata."""
        write_json_file(
            self._run_base
            / record.derived_id
            / f"v{record.version}"
            / f"{record.run_id}.json",
            record.to_json_dict(),
        )

    def write_state(self, record: DerivedStateRecord) -> None:
        """Persist latest state metadata."""
        write_json_file(
            self._state_base / f"{record.derived_id}.json",
            record.to_json_dict(),
        )

    def write_partitions(self, records: tuple[DerivedPartitionRecord, ...]) -> None:
        """Persist partition metadata for a run."""
        for record in records:
            write_json_file(
                self._partition_base
                / record.derived_id
                / f"v{record.version}"
                / record.run_id
                / f"{record.partition_key}.json",
                record.to_json_dict(),
            )
