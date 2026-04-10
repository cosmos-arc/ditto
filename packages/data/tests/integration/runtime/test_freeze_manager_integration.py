"""Tests for FreezeManager."""

import shutil
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

import orjson
import pytest
from ditto_data.runtime.freeze_manager import FreezeManager


class TestFreezeManager:
    """Test cases for FreezeManager."""

    def setup_method(self) -> None:
        """Set up test environment."""
        self.temp_dir = TemporaryDirectory()
        self.data_root = Path(self.temp_dir.name)

        # Create test data files
        self.bars_dir = self.data_root / "bars"
        self.bars_dir.mkdir(parents=True)

        # Create test files with known content
        (self.bars_dir / "stock_daily.parquet").write_bytes(b"stock_data_2020")
        (self.bars_dir / "etf_daily.parquet").write_bytes(b"etf_data_2024")

        # Create some other files not in the freeze
        (self.bars_dir / "other_file.parquet").write_bytes(b"other_data")

        # Initialize FreezeManager
        self.manager = FreezeManager(str(self.data_root))

    def teardown_method(self) -> None:
        """Clean up test environment."""
        self.temp_dir.cleanup()

    def test_create_freeze_generates_manifest_with_checksums(self) -> None:
        """Test creating freeze generates checksum manifest."""
        manifest = self.manager.create(
            freeze_id="backtest_v1",
            description="首次回测版本",
            datasets=["bars/stock_daily", "bars/etf_daily"],
        )

        assert manifest.freeze_id == "backtest_v1"
        assert manifest.description == "首次回测版本"
        assert manifest.file_count == 2

        # Check files have checksums
        assert "bars/stock_daily.parquet" in manifest.files
        assert "bars/etf_daily.parquet" in manifest.files

        # Verify checksums are SHA-256 format (64 hex chars)
        for checksum in manifest.files.values():
            assert len(checksum) == 64
            assert all(c in "0123456789abcdef" for c in checksum)
        # Verify new version and checksum_type fields
        assert manifest.version == "2.0"
        assert manifest.checksum_type == "sha256"

    def test_create_freeze_saves_manifest_to_disk(self) -> None:
        """Test freeze manifest is persisted to disk."""
        manifest = self.manager.create(
            freeze_id="backtest_v1",
            description="首次回测版本",
            datasets=["bars/stock_daily"],
        )

        # Check manifest file exists
        manifest_path = self.data_root / "freezes" / "backtest_v1.json"
        assert manifest_path.exists()

        # Check we can read it back
        loaded = self.manager.get_manifest("backtest_v1")
        assert loaded.freeze_id == "backtest_v1"
        assert loaded.files == manifest.files

    def test_verify_freeze_success(self) -> None:
        """Test verifying a valid freeze passes."""
        self.manager.create(
            freeze_id="backtest_v1",
            description="首次回测版本",
            datasets=["bars/stock_daily", "bars/etf_daily"],
        )

        passed, errors = self.manager.verify("backtest_v1")

        assert passed is True
        assert errors == []

    def test_verify_freeze_fails_when_file_modified(self) -> None:
        """Test verifying freeze fails when file is modified."""
        self.manager.create(
            freeze_id="backtest_v1",
            description="首次回测版本",
            datasets=["bars/stock_daily"],
        )

        # Modify the file
        (self.bars_dir / "stock_daily.parquet").write_bytes(b"modified_data")

        passed, errors = self.manager.verify("backtest_v1")

        assert passed is False
        assert len(errors) == 1
        assert "bars/stock_daily.parquet" in errors[0]

    def test_verify_freeze_fails_when_file_missing(self) -> None:
        """Test verifying freeze fails when file is missing."""
        self.manager.create(
            freeze_id="backtest_v1",
            description="首次回测版本",
            datasets=["bars/stock_daily"],
        )

        # Delete the file
        (self.bars_dir / "stock_daily.parquet").unlink()

        passed, errors = self.manager.verify("backtest_v1")

        assert passed is False
        assert len(errors) == 1
        assert "missing" in errors[0].lower() or "not found" in errors[0].lower()

    def test_verify_raise_on_error(self) -> None:
        """Test verify raises exception when raise_on_error=True."""
        self.manager.create(
            freeze_id="backtest_v1",
            description="首次回测版本",
            datasets=["bars/stock_daily"],
        )

        # Modify the file
        (self.bars_dir / "stock_daily.parquet").write_bytes(b"modified_data")

        with pytest.raises(RuntimeError, match="Freeze verification failed"):
            self.manager.verify("backtest_v1", raise_on_error=True)

    def test_list_freezes(self) -> None:
        """Test listing all freezes."""
        self.manager.create(
            freeze_id="backtest_v1",
            description="首次回测",
            datasets=["bars/stock_daily"],
        )
        self.manager.create(
            freeze_id="backtest_v2",
            description="第二次回测",
            datasets=["bars/etf_daily"],
        )

        freezes = self.manager.list_freezes()

        assert len(freezes) == 2
        freeze_ids = {f.freeze_id for f in freezes}
        assert freeze_ids == {"backtest_v1", "backtest_v2"}

    def test_get_manifest(self) -> None:
        """Test getting manifest by ID."""
        created = self.manager.create(
            freeze_id="backtest_v1",
            description="首次回测版本",
            datasets=["bars/stock_daily"],
        )

        retrieved = self.manager.get_manifest("backtest_v1")

        assert retrieved.freeze_id == created.freeze_id
        assert retrieved.description == created.description
        assert retrieved.files == created.files

    def test_get_manifest_not_found(self) -> None:
        """Test getting non-existent manifest raises error."""
        with pytest.raises(FileNotFoundError):
            self.manager.get_manifest("nonexistent")

    def test_delete_freeze(self) -> None:
        """Test deleting a freeze."""
        self.manager.create(
            freeze_id="backtest_v1",
            description="首次回测版本",
            datasets=["bars/stock_daily"],
        )

        manifest_path = self.data_root / "freezes" / "backtest_v1.json"
        assert manifest_path.exists()

        self.manager.delete("backtest_v1")

        assert not manifest_path.exists()

        # Should no longer be in list
        freezes = self.manager.list_freezes()
        assert "backtest_v1" not in {f.freeze_id for f in freezes}

    def test_datasets_filter_by_pattern(self) -> None:
        """Test dataset pattern filtering."""
        # Create multiple files under different prefixes
        (self.bars_dir / "stock_2020.parquet").write_bytes(b"data1")
        (self.bars_dir / "stock_2021.parquet").write_bytes(b"data2")
        (self.bars_dir / "etf_2024.parquet").write_bytes(b"data3")

        # Use pattern to match only stock_ files
        manifest = self.manager.create(
            freeze_id="pattern_test",
            description="测试模式匹配",
            datasets=["bars/stock_2020"],  # Exact match needed
        )

        # Only matching files should be included
        assert manifest.file_count == 1
        assert "bars/stock_2020.parquet" in manifest.files

    def test_create_freeze_with_missing_dataset_raises_error(self) -> None:
        """Test creating freeze with non-existent dataset raises error."""
        with pytest.raises(FileNotFoundError, match="Datasets not found"):
            self.manager.create(
                freeze_id="missing_test",
                description="测试缺失文件",
                datasets=["bars/nonexistent", "bars/stock_daily"],
            )

    def test_create_freeze_with_invalid_freeze_id_raises_error(self) -> None:
        """Test creating freeze with invalid freeze_id raises error."""
        # Test with path separator
        with pytest.raises(ValueError, match="Invalid freeze_id"):
            self.manager.create(
                freeze_id="backtest/v1",
                description="Invalid ID",
                datasets=["bars/stock_daily"],
            )

        # Test with backslash
        with pytest.raises(ValueError, match="Invalid freeze_id"):
            self.manager.create(
                freeze_id="backtest\\v1",
                description="Invalid ID",
                datasets=["bars/stock_daily"],
            )

        # Test with double dots
        with pytest.raises(ValueError, match="Invalid freeze_id"):
            self.manager.create(
                freeze_id="../backtest",
                description="Invalid ID",
                datasets=["bars/stock_daily"],
            )

    def test_manifest_created_at_format(self) -> None:
        """Test manifest has ISO format timestamp."""
        manifest = self.manager.create(
            freeze_id="backtest_v1",
            description="首次回测版本",
            datasets=["bars/stock_daily"],
        )

        # Should be parseable as ISO datetime
        datetime.fromisoformat(manifest.created_at)

    def test_cleanup_expired(self) -> None:
        """Test cleanup of expired freezes."""
        # Create manager with 90 days default TTL
        manager = FreezeManager(str(self.data_root), default_ttl_days=90)

        # Create current freeze (should not be deleted)
        manager.create(
            freeze_id="current_freeze",
            description="Current freeze",
            datasets=["bars/stock_daily"],
        )

        # Create old freeze (should be deleted)
        old_manifest = manager.create(
            freeze_id="old_freeze",
            description="Old freeze",
            datasets=["bars/etf_daily"],
        )

        # Mock created_at for old freeze to be 100 days ago
        old_manifest_path = self.data_root / "freezes" / "old_freeze.json"
        with old_manifest_path.open("w", encoding="utf-8") as f:
            data = {
                "freeze_id": "old_freeze",
                "description": "Old freeze",
                "created_at": (datetime.now() - timedelta(days=100)).isoformat(),
                "version": "2.0",
                "checksum_type": "sha256",
                "files": old_manifest.files,
            }
            json_bytes = orjson.dumps(
                data,
                option=orjson.OPT_INDENT_2
                | orjson.OPT_NON_STR_KEYS
                | orjson.OPT_OMIT_MICROSECONDS,
            )
            f.write(json_bytes.decode("utf-8"))

        # Run cleanup with 90 days max age
        deleted = manager.cleanup_expired(max_age_days=90)

        # Should have deleted old_freeze but not current_freeze
        assert "old_freeze" in deleted
        assert "current_freeze" not in deleted
        assert len(deleted) == 1

        # Verify old freeze is actually deleted
        with pytest.raises(FileNotFoundError):
            manager.get_manifest("old_freeze")

        # Verify current freeze still exists
        current = manager.get_manifest("current_freeze")
        assert current.freeze_id == "current_freeze"

    def test_cleanup_expired_with_default_ttl(self) -> None:
        """Test cleanup using default TTL."""
        # Create manager with 30 days default TTL
        manager = FreezeManager(str(self.data_root), default_ttl_days=30)

        # Create old freeze (should be deleted)
        old_manifest = manager.create(
            freeze_id="old_freeze",
            description="Old freeze",
            datasets=["bars/stock_daily"],
        )

        # Mock created_at for old freeze to be 40 days ago
        old_manifest_path = self.data_root / "freezes" / "old_freeze.json"
        with old_manifest_path.open("w", encoding="utf-8") as f:
            data = {
                "freeze_id": "old_freeze",
                "description": "Old freeze",
                "created_at": (datetime.now() - timedelta(days=40)).isoformat(),
                "version": "2.0",
                "checksum_type": "sha256",
                "files": old_manifest.files,
            }
            json_bytes = orjson.dumps(
                data,
                option=orjson.OPT_INDENT_2
                | orjson.OPT_NON_STR_KEYS
                | orjson.OPT_OMIT_MICROSECONDS,
            )
            f.write(json_bytes.decode("utf-8"))

        # Run cleanup without specifying max_age_days (should use default)
        deleted = manager.cleanup_expired()

        # Should have deleted old_freeze
        assert "old_freeze" in deleted

    def test_cleanup_expired_nothing_to_delete(self) -> None:
        """Test cleanup when no freezes are expired."""
        # Create current freeze (should not be deleted)
        manager = FreezeManager(str(self.data_root), default_ttl_days=90)
        manager.create(
            freeze_id="current_freeze",
            description="Current freeze",
            datasets=["bars/stock_daily"],
        )

        # Run cleanup with 1 day max age (nothing should be deleted)
        deleted = manager.cleanup_expired(max_age_days=1)

        # Should not delete anything
        assert deleted == []

    def test_cleanup_expired_empty_directory(self) -> None:
        """Test cleanup when freezes directory is empty."""
        # Create new manager without creating any freezes
        # Remove existing freezes directory if it exists
        freezes_dir = self.data_root / "freezes"
        if freezes_dir.exists():
            shutil.rmtree(freezes_dir)

        manager = FreezeManager(str(self.data_root))

        # Run cleanup
        deleted = manager.cleanup_expired(max_age_days=90)

        # Should return empty list
        assert deleted == []
