"""Unit tests for Models - storage."""

import dataclasses

import pytest
from ditto_platform.foundation import (
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
