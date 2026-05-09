"""Tests for publication safety manifest stores."""

from pathlib import Path

from ditto_features.publication_safety_records import CompatibilityManifestRecord
from ditto_features.storage.runtime.publication_safety import (
    ManifestReader,
    ManifestWriter,
)


class TestManifestStore:
    """Tests for manifest reader/writer."""

    def test_manifest_roundtrip(self, tmp_path: Path) -> None:
        """Test manifest can be written and read back by derived/version."""
        writer = ManifestWriter(base_path=tmp_path)
        reader = ManifestReader(base_path=tmp_path)
        record = CompatibilityManifestRecord(
            derived_id="factor.momentum_20d",
            version=3,
            manifest_hash="manifest-hash-v3",
            payload={
                "engine_codegen_version": "codegen-v1",
                "analysis_version": "analysis-v1",
            },
            created_at="2026-03-13T12:00:00+08:00",
        )

        writer.write_manifest(record)
        loaded = reader.read_manifest("factor.momentum_20d", 3)

        assert loaded == record

    def test_missing_manifest_returns_none(self, tmp_path: Path) -> None:
        """Test missing manifest returns None."""
        reader = ManifestReader(base_path=tmp_path)

        assert reader.read_manifest("factor.momentum_20d", 99) is None
