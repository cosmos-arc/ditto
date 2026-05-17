"""Writer for publication safety manifests."""

from pathlib import Path

from ditto_features.publication_safety_records import CompatibilityManifestRecord
from ditto_features.storage.runtime.publication_safety._json_records import (
    write_json_file,
)


class ManifestWriter:
    """File-based writer for compatibility manifests."""

    def __init__(self, base_path: Path) -> None:
        self._base_path = (
            Path(base_path) / "derived" / "publication_safety" / "manifests"
        )
        self._base_path.mkdir(parents=True, exist_ok=True)

    def write_manifest(self, record: CompatibilityManifestRecord) -> None:
        """Persist a compatibility manifest record."""
        file_path = self._base_path / record.derived_id / f"v{record.version}.json"
        write_json_file(file_path, record.to_json_dict())
