"""Reader for derived catalog runtime metadata."""

from __future__ import annotations

from pathlib import Path

from ditto_datahub.models.derived import (
    DerivedPartitionRecord,
    DerivedRunRecord,
    DerivedSpecRecord,
    DerivedStateRecord,
    DerivedVersionRecord,
)
from ditto_datahub.stores.runtime.derived_catalog._json_records import (
    list_json_files,
    read_json_file,
)


class DerivedCatalogReader:
    """File-based reader for derived catalog runtime metadata."""

    def __init__(self, base_path: Path) -> None:
        root = Path(base_path) / "derived" / "catalog"
        self._spec_base = root / "specs"
        self._version_base = root / "versions"
        self._state_base = root / "state"
        self._run_base = root / "runs"
        self._partition_base = root / "partitions"

    def read_spec(self, derived_id: str, version: int) -> DerivedSpecRecord | None:
        """Read spec metadata by derived/version."""
        payload = read_json_file(self._spec_base / derived_id / f"v{version}.json")
        if payload is None:
            return None
        return DerivedSpecRecord.from_json_dict(payload)

    def read_version(
        self,
        derived_id: str,
        version: int,
    ) -> DerivedVersionRecord | None:
        """Read version metadata by derived/version."""
        payload = read_json_file(self._version_base / derived_id / f"v{version}.json")
        if payload is None:
            return None
        return DerivedVersionRecord.from_json_dict(payload)

    def read_run(
        self,
        derived_id: str,
        version: int,
        run_id: str,
    ) -> DerivedRunRecord | None:
        """Read run metadata by derived/version/run id."""
        payload = read_json_file(
            self._run_base / derived_id / f"v{version}" / f"{run_id}.json"
        )
        if payload is None:
            return None
        return DerivedRunRecord.from_json_dict(payload)

    def get_latest_run(self, derived_id: str, version: int) -> DerivedRunRecord | None:
        """Return the latest run for a derived/version."""
        run_dir = self._run_base / derived_id / f"v{version}"
        records: list[DerivedRunRecord] = []
        for file_path in list_json_files(run_dir):
            payload = read_json_file(file_path)
            if payload is None:
                continue
            records.append(DerivedRunRecord.from_json_dict(payload))

        if not records:
            return None
        return max(records, key=lambda record: (record.created_at, record.run_id))

    def read_state(self, derived_id: str) -> DerivedStateRecord | None:
        """Read latest derived state by derived id."""
        payload = read_json_file(self._state_base / f"{derived_id}.json")
        if payload is None:
            return None
        return DerivedStateRecord.from_json_dict(payload)

    def list_partitions(
        self,
        derived_id: str,
        version: int,
        run_id: str,
    ) -> list[DerivedPartitionRecord]:
        """List partition metadata for a run."""
        partition_dir = self._partition_base / derived_id / f"v{version}" / run_id
        partitions: list[DerivedPartitionRecord] = []
        for file_path in list_json_files(partition_dir):
            payload = read_json_file(file_path)
            if payload is None:
                continue
            partitions.append(DerivedPartitionRecord.from_json_dict(payload))

        return sorted(
            partitions,
            key=lambda record: (record.partition_key, record.written_at),
        )
