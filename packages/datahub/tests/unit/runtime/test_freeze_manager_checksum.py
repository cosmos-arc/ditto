"""Tests for FreezeManager SHA-256 checksum migration."""

import hashlib
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from ditto_datahub.runtime.freeze_manager import FreezeManager


class TestFreezeManagerChecksum:
    """Test FreezeManager checksum functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.manager = FreezeManager(str(self.temp_dir))

    def teardown_method(self):
        """Clean up test fixtures."""
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_sha256_checksum_default(self):
        """Test that new freeze manifests use SHA-256 by default."""
        # Create a test file
        test_file = self.temp_dir / "test.parquet"
        test_file.write_text("test data")

        # Create freeze
        manifest = self.manager.create(
            freeze_id="test_freeze",
            description="Test freeze",
            datasets=["test"],
        )

        # Verify checksum type is SHA-256
        assert manifest.checksum_type == "sha256"
        # Verify version is 2.0
        assert manifest.version == "2.0"
        # Verify checksum length is 64 (SHA-256)
        checksum = list(manifest.files.values())[0]
        assert len(checksum) == 64
        # Verify SHA-256 format (hexadecimal)
        assert all(c in "0123456789abcdef" for c in checksum)

    def test_backward_compatibility_md5(self):
        """Test that old manifests with MD5 can still be loaded and verified."""
        # Create a test file
        test_file = self.temp_dir / "test.parquet"
        test_file.write_text("test data")

        # Create an old-style manifest with MD5
        old_manifest_path = self.temp_dir / "freezes" / "old_freeze.json"
        self.temp_dir / "freezes" / "old_freeze.json"
        old_manifest_path.parent.mkdir(exist_ok=True)

        # Calculate MD5 checksum
        import hashlib

        md5 = hashlib.md5(usedforsecurity=False)
        md5.update(test_file.read_bytes())
        md5_checksum = md5.hexdigest()

        # Create old manifest format
        old_manifest_data = {
            "freeze_id": "old_freeze",
            "description": "Old freeze",
            "created_at": "2024-01-01T00:00:00",
            "files": {"test.parquet": md5_checksum},
        }

        with old_manifest_path.open("w", encoding="utf-8") as f:
            json.dump(old_manifest_data, f, indent=2, ensure_ascii=False)

        # Load old manifest
        manifest = self.manager.get_manifest("old_freeze")

        # Verify it loads correctly
        assert manifest.freeze_id == "old_freeze"
        assert manifest.checksum_type == "md5"  # Old format defaults to MD5
        assert manifest.version == "1.0"  # Old format defaults to version 1.0
        assert len(next(iter(manifest.files.values()))) == 32  # MD5 length

        # Verify checksum still matches
        actual_checksum = self.manager._compute_md5_checksum(test_file)
        assert actual_checksum == next(iter(manifest.files.values()))

    def test_sha256_vs_md5_different_checksums(self):
        """Test that SHA-256 and MD5 produce different checksums for the same file."""
        # Create a test file
        test_file = self.temp_dir / "test.parquet"
        test_file.write_text("test data")

        # Test current SHA-256 implementation
        sha256_checksum = self.manager._compute_checksum(test_file)

        # Test MD5 implementation
        md5 = hashlib.md5(usedforsecurity=False)
        md5.update(test_file.read_bytes())
        md5_checksum = md5.hexdigest()

        # Verify they are different
        assert sha256_checksum != md5_checksum
        assert len(sha256_checksum) == 64  # SHA-256
        assert len(md5_checksum) == 32  # MD5

    def test_freeze_manifest_new_fields(self):
        """Test that FreezeManifest has new fields for version and checksum_type."""
        # Create a test file
        test_file = self.temp_dir / "test.parquet"
        test_file.write_text("test data")

        # Create freeze
        manifest = self.manager.create(
            freeze_id="test_freeze",
            description="Test freeze",
            datasets=["test"],
        )

        # Verify new fields exist
        assert hasattr(manifest, "version")
        assert hasattr(manifest, "checksum_type")
        assert manifest.version == "2.0"
        assert manifest.checksum_type == "sha256"

    def test_save_load_manifest_with_new_fields(self):
        """Test that manifest with new fields can be saved and loaded correctly."""
        # Create a test file
        test_file = self.temp_dir / "test.parquet"
        test_file.write_text("test data")

        # Create freeze
        original_manifest = self.manager.create(
            freeze_id="test_freeze",
            description="Test freeze",
            datasets=["test"],
        )

        # Reload from disk
        reloaded_manifest = self.manager.get_manifest("test_freeze")

        # Verify all fields match
        assert reloaded_manifest.freeze_id == original_manifest.freeze_id
        assert reloaded_manifest.description == original_manifest.description
        assert reloaded_manifest.created_at == original_manifest.created_at
        assert reloaded_manifest.version == original_manifest.version
        assert reloaded_manifest.checksum_type == original_manifest.checksum_type
        assert reloaded_manifest.files == original_manifest.files

    @patch("ditto_datahub.runtime.freeze_manager.hashlib")
    def test_compute_checksum_implementation(self, mock_hashlib):
        """Test the _compute_checksum implementation uses SHA-256."""
        # Mock hashlib.sha256
        mock_sha256 = mock_hashlib.sha256.return_value
        mock_sha256.hexdigest.return_value = "mock_sha256_hash"

        # Create a test file
        test_file = self.temp_dir / "test.parquet"
        test_file.write_text("test data")

        # Call _compute_checksum
        result = self.manager._compute_checksum(test_file)

        # Verify SHA-256 was used
        mock_hashlib.sha256.assert_called_once()
        mock_sha256.update.assert_called()
        assert result == "mock_sha256_hash"

        # Verify MD5 was NOT used
        mock_hashlib.md5.assert_not_called()
