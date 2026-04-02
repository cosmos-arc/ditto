"""Unit tests for Models - storage."""

import dataclasses

import pytest
from ditto_data.models.storage import (
    FreezeManifest,
    WriteResult,
    WriteStoreResult,
)


@pytest.mark.unit
class TestWriteResult:
    """Tests for WriteResult model."""

    def test_create_write_result_success(self) -> None:
        """Test creating WriteResult for successful write."""
        result = WriteResult(
            file_path="/data/stock_daily/2024-01-02.parquet",
            checksum="abc123",
            rows_written=1000,
            rows_total=1000,
            blocked=False,
        )

        assert result.file_path == "/data/stock_daily/2024-01-02.parquet"
        assert result.checksum == "abc123"
        assert result.rows_written == 1000
        assert result.rows_total == 1000
        assert result.blocked is False

    def test_create_write_result_blocked(self) -> None:
        """Test creating WriteResult for blocked write."""
        result = WriteResult(
            file_path="/data/stock_daily/2024-01-02.parquet",
            checksum="abc123",
            rows_written=0,
            rows_total=1000,
            blocked=True,
        )

        assert result.blocked is True
        assert result.rows_written == 0

    def test_write_result_is_frozen(self) -> None:
        """Test that WriteResult is frozen (immutable)."""
        result = WriteResult(
            file_path="/data/test.parquet",
            checksum="xyz",
            rows_written=100,
            rows_total=100,
            blocked=False,
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            result.file_path = "/other/path"


@pytest.mark.unit
class TestWriteStoreResult:
    """Tests for WriteStoreResult model."""

    def test_create_write_result_store_added(self) -> None:
        """Test creating WriteStoreResult for added rows."""
        result = WriteStoreResult(
            file_path="/data/stock_daily/2024-01-02.parquet",
            checksum="abc123",
            added=1000,
            updated=0,
            skipped=0,
            is_merge=False,
        )

        assert result.file_path == "/data/stock_daily/2024-01-02.parquet"
        assert result.checksum == "abc123"
        assert result.added == 1000
        assert result.updated == 0
        assert result.skipped == 0
        assert result.is_merge is False

    def test_create_write_result_store_updated(self) -> None:
        """Test creating WriteStoreResult for updated rows."""
        result = WriteStoreResult(
            file_path="/data/stock_daily/2024-01-02.parquet",
            checksum="abc123",
            added=0,
            updated=500,
            skipped=0,
            is_merge=True,
        )

        assert result.updated == 500
        assert result.added == 0
        assert result.is_merge is True

    def test_create_write_result_store_skipped(self) -> None:
        """Test creating WriteStoreResult with skipped rows."""
        result = WriteStoreResult(
            file_path="/data/stock_daily/2024-01-02.parquet",
            checksum="abc123",
            added=0,
            updated=0,
            skipped=100,
            is_merge=False,
        )

        assert result.skipped == 100
        assert result.added == 0
        assert result.updated == 0

    def test_write_result_store_is_frozen(self) -> None:
        """Test that WriteStoreResult is frozen (immutable)."""
        result = WriteStoreResult(
            file_path="/data/test.parquet",
            checksum="xyz",
            added=100,
            updated=0,
            skipped=0,
            is_merge=False,
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            result.added = 200


@pytest.mark.unit
class TestFreezeManifest:
    """Tests for FreezeManifest model."""

    def test_create_freeze_manifest(self) -> None:
        """Test creating FreezeManifest."""
        manifest = FreezeManifest(
            freeze_id="freeze_20240102_120000",
            description="Daily data freeze",
            created_at="2024-01-02T12:00:00Z",
        )

        assert manifest.freeze_id == "freeze_20240102_120000"
        assert manifest.description == "Daily data freeze"
        assert manifest.created_at == "2024-01-02T12:00:00Z"
        assert manifest.version == "2.0"
        assert manifest.checksum_type == "sha256"
        assert manifest.files == {}

    def test_freeze_manifest_with_custom_version(self) -> None:
        """Test creating FreezeManifest with custom version."""
        manifest = FreezeManifest(
            freeze_id="freeze_20240102_120000",
            description="Test freeze",
            created_at="2024-01-02T12:00:00Z",
            version="1.0",
            checksum_type="md5",
        )

        assert manifest.version == "1.0"
        assert manifest.checksum_type == "md5"

    def test_freeze_manifest_with_files(self) -> None:
        """Test creating FreezeManifest with files."""
        manifest = FreezeManifest(
            freeze_id="freeze_20240102_120000",
            description="Daily data freeze",
            created_at="2024-01-02T12:00:00Z",
            files={
                "stock_daily/2024-01-02.parquet": "abc123",
                "stock_daily/2024-01-03.parquet": "def456",
            },
        )

        assert manifest.file_count == 2
        assert manifest.files["stock_daily/2024-01-02.parquet"] == "abc123"
        assert manifest.files["stock_daily/2024-01-03.parquet"] == "def456"

    def test_freeze_manifest_file_count_property(self) -> None:
        """Test FreezeManifest file_count property."""
        manifest = FreezeManifest(
            freeze_id="freeze_20240102_120000",
            description="Test freeze",
            created_at="2024-01-02T12:00:00Z",
            files={
                "file1.parquet": "abc123",
                "file2.parquet": "def456",
                "file3.parquet": "ghi789",
            },
        )

        assert manifest.file_count == 3

    def test_freeze_manifest_is_frozen(self) -> None:
        """Test that FreezeManifest is frozen (immutable)."""
        manifest = FreezeManifest(
            freeze_id="freeze_20240102_120000",
            description="Test freeze",
            created_at="2024-01-02T12:00:00:00Z",
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            manifest.description = "Modified description"
