"""Unit tests for FileLockManager."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from ditto_foundation.concurrency.filelock import (
    FileLockManager,
    LockAcquisitionError,
)
from filelock import Timeout


@pytest.mark.unit
class TestFileLockManager:
    """Tests for FileLockManager."""

    def test_initialization_requires_lock_dir(self) -> None:
        """Test that FileLockManager requires lock_dir parameter."""
        # FileLockManager requires lock_dir parameter
        lock_dir = Path("/test/locks")
        manager = FileLockManager(lock_dir=lock_dir)
        assert manager.lock_dir == lock_dir

    def test_initialization_with_custom_lock_dir(self) -> None:
        """Test initialization with custom lock directory."""
        lock_dir = Path("/custom/lock/dir")
        manager = FileLockManager(lock_dir=lock_dir)
        assert manager.lock_dir == lock_dir

    @patch("ditto_foundation.concurrency.filelock.FileLock")
    def test_acquire_creates_lock_file(self, mock_filelock_class: MagicMock) -> None:
        """Test that acquire creates lock file."""
        lock_dir = Path("/test/locks")
        manager = FileLockManager(lock_dir=lock_dir)

        mock_lock = MagicMock()
        mock_lock.__enter__ = MagicMock(return_value=None)
        mock_lock.__exit__ = MagicMock(return_value=None)
        mock_filelock_class.return_value = mock_lock

        with manager.acquire("test_lock"):
            mock_lock.__enter__.assert_called_once()

        # Verify FileLock was created with correct path
        mock_filelock_class.assert_called_once()
        call_args = mock_filelock_class.call_args
        assert call_args[0][0] == lock_dir / "test_lock.lock"

    @patch("ditto_foundation.concurrency.filelock.FileLock")
    def test_acquire_creates_lock_dir_if_not_exists(
        self, mock_filelock_class: MagicMock
    ) -> None:
        """Test that acquire creates lock directory if not exists."""
        lock_dir = Path("/test/locks")
        manager = FileLockManager(lock_dir=lock_dir)

        mock_lock = MagicMock()
        mock_lock.__enter__ = MagicMock(return_value=None)
        mock_lock.__exit__ = MagicMock(return_value=None)
        mock_filelock_class.return_value = mock_lock

        with manager.acquire("test_lock"):
            mock_lock.__enter__.assert_called_once()

        # Verify FileLock was called
        mock_filelock_class.assert_called_once()

    @patch("ditto_foundation.concurrency.filelock.FileLock")
    def test_acquire_with_default_timeout(self, mock_filelock_class: MagicMock) -> None:
        """Test acquire with default timeout."""
        manager = FileLockManager(lock_dir=Path("/test/locks"))

        mock_lock = MagicMock()
        mock_lock.__enter__ = MagicMock(return_value=None)
        mock_lock.__exit__ = MagicMock(return_value=None)
        mock_filelock_class.return_value = mock_lock

        with manager.acquire("test_lock"):
            mock_lock.__enter__.assert_called_once()

        # Verify FileLock was created with default timeout
        call_args = mock_filelock_class.call_args
        assert call_args[1]["timeout"] == 30.0

    @patch("ditto_foundation.concurrency.filelock.FileLock")
    def test_acquire_with_custom_timeout(self, mock_filelock_class: MagicMock) -> None:
        """Test acquire with custom timeout."""
        manager = FileLockManager(lock_dir=Path("/test/locks"))

        mock_lock = MagicMock()
        mock_lock.__enter__ = MagicMock(return_value=None)
        mock_lock.__exit__ = MagicMock(return_value=None)
        mock_filelock_class.return_value = mock_lock

        with manager.acquire("test_lock", timeout=60.0):
            mock_lock.__enter__.assert_called_once()

        # Verify FileLock was created with custom timeout
        call_args = mock_filelock_class.call_args
        assert call_args[1]["timeout"] == 60.0

    @patch("ditto_foundation.concurrency.filelock.FileLock")
    def test_acquire_raises_error_on_timeout(
        self, mock_filelock_class: MagicMock
    ) -> None:
        """Test that acquire raises LockAcquisitionError on timeout."""
        manager = FileLockManager(lock_dir=Path("/test/locks"))

        # Mock FileLock to raise Timeout
        mock_lock = MagicMock()
        mock_lock.__enter__.side_effect = Timeout("Lock timeout")
        mock_filelock_class.return_value = mock_lock

        with pytest.raises(LockAcquisitionError) as exc_info:
            with manager.acquire("test_lock"):
                mock_lock.__enter__.assert_called_once()

        assert "test_lock" in str(exc_info.value)
        # Error message says "within" not "timeout"
        assert "within" in str(exc_info.value).lower()

    @patch("ditto_foundation.concurrency.filelock.FileLock")
    def test_acquire_releases_lock_after_context(
        self, mock_filelock_class: MagicMock
    ) -> None:
        """Test that acquire releases lock after context."""
        manager = FileLockManager(lock_dir=Path("/test/locks"))

        mock_lock = MagicMock()
        mock_lock.__enter__ = MagicMock(return_value=None)
        mock_lock.__exit__ = MagicMock(return_value=None)
        mock_filelock_class.return_value = mock_lock

        with manager.acquire("test_lock"):
            # Inside context, lock is held
            mock_lock.__enter__.assert_called_once()

        # After context, lock is released
        mock_lock.__exit__.assert_called_once()

    @patch("ditto_foundation.concurrency.filelock.FileLock")
    def test_acquire_with_multiple_locks(self, mock_filelock_class: MagicMock) -> None:
        """Test acquiring multiple different locks."""
        manager = FileLockManager(lock_dir=Path("/test/locks"))

        mock_lock = MagicMock()
        mock_lock.__enter__ = MagicMock(return_value=None)
        mock_lock.__exit__ = MagicMock(return_value=None)
        mock_filelock_class.return_value = mock_lock

        with manager.acquire("lock1"):
            with manager.acquire("lock2"):
                mock_lock.__enter__.assert_called()

        # Verify FileLock was called twice with different paths
        assert mock_filelock_class.call_count == 2

    @patch("ditto_foundation.concurrency.filelock.FileLock")
    def test_acquire_normalizes_lock_name(self, mock_filelock_class: MagicMock) -> None:
        """Test that lock names are normalized correctly."""
        manager = FileLockManager(lock_dir=Path("/test/locks"))

        mock_lock = MagicMock()
        mock_lock.__enter__ = MagicMock(return_value=None)
        mock_lock.__exit__ = MagicMock(return_value=None)
        mock_filelock_class.return_value = mock_lock

        with manager.acquire("test_lock"):
            mock_lock.__enter__.assert_called_once()

        # Verify .lock suffix is added
        call_args = mock_filelock_class.call_args
        assert call_args[0][0].name == "test_lock.lock"

    @patch("ditto_foundation.concurrency.filelock.FileLock")
    def test_acquire_with_special_characters_in_name(
        self, mock_filelock_class: MagicMock
    ) -> None:
        """Test acquire with special characters in lock name."""
        manager = FileLockManager(lock_dir=Path("/test/locks"))

        mock_lock = MagicMock()
        mock_lock.__enter__ = MagicMock(return_value=None)
        mock_lock.__exit__ = MagicMock(return_value=None)
        mock_filelock_class.return_value = mock_lock

        # Lock names with path separators or special chars
        with manager.acquire("data/ingestion/stock"):
            mock_lock.__enter__.assert_called_once()

        call_args = mock_filelock_class.call_args
        # The name should be used as-is with .lock suffix
        # Use Path.name to get just the filename without path
        lock_path_str = str(call_args[0][0])
        # Normalize path separators for comparison
        assert "data" in lock_path_str
        assert "ingestion" in lock_path_str
        assert "stock.lock" in lock_path_str
