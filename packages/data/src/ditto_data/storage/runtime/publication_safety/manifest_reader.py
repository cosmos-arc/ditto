"""Reader for publication safety manifests."""

from pathlib import Path

from ditto_kernel.publication_safety import CompatibilityManifestRecord

from ditto_data.storage.runtime.publication_safety._json_records import read_json_file


class ManifestReader:
    """File-based reader for compatibility manifests."""

    def __init__(self, base_path: Path) -> None:
        self._base_path = (
            Path(base_path) / "derived" / "publication_safety" / "manifests"
        )

    def read_manifest(
        self,
        derived_id: str,
        version: int,
    ) -> CompatibilityManifestRecord | None:
        """Read a compatibility manifest record by derived/version."""
        file_path = self._base_path / derived_id / f"v{version}.json"
        payload = read_json_file(file_path)
        if payload is None:
            return None
        return CompatibilityManifestRecord.from_json_dict(payload)
