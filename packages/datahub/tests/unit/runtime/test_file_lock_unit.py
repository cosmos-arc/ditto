"""Tests for File Lock Manager."""

import shutil
import tempfile
import time
from pathlib import Path
from threading import Thread
from time import sleep

import pytest
from ditto_datahub.runtime.file_lock import FileLockManager, LockAcquisitionError


class TestFileLockManager:
    """Test cases for FileLockManager."""

    def setup_method(self) -> None:
        """Set up test environment."""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.lock_manager = FileLockManager(self.temp_dir)

    def teardown_method(self) -> None:
        """Clean up test environment."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_basic_lock_functionality(self) -> None:
        """Test basic lock functionality using context manager."""
        lock_name = "test_lock"

        # Acquire lock using context manager
        with self.lock_manager.acquire(lock_name):
            # Lock is held within this context
            pass

        # Lock is released after context

    def test_concurrent_lock_prevention(self) -> None:
        """Test that concurrent access is prevented."""
        lock_name = "concurrent_test"
        results = []

        def try_acquire_lock(result_index: int) -> None:
            try:
                with self.lock_manager.acquire(lock_name, timeout=0.1):
                    results.append(f"lock_acquired_{result_index}")
                    sleep(0.3)  # Hold lock longer than timeout
            except LockAcquisitionError:
                results.append(f"lock_failed_{result_index}")

        # Start two threads trying to acquire the same lock
        thread1 = Thread(target=try_acquire_lock, args=(1,))
        thread2 = Thread(target=try_acquire_lock, args=(2,))

        thread1.start()
        thread2.start()  # Start immediately to create contention

        thread1.join()
        thread2.join()

        # One should succeed, one should fail
        assert len(results) == 2
        assert any("lock_acquired_" in r for r in results)
        assert any("lock_failed_" in r for r in results)

    def test_lock_timeout(self) -> None:
        """Test lock timeout functionality."""
        lock_name = "timeout_test"

        def hold_lock() -> None:
            with self.lock_manager.acquire(lock_name):
                sleep(0.5)

        # Start thread that will hold the lock
        thread = Thread(target=hold_lock)
        thread.start()

        sleep(0.1)  # Let thread acquire lock

        # Try to acquire with short timeout - should fail
        start_time = time.time()
        with pytest.raises(LockAcquisitionError):
            with self.lock_manager.acquire(lock_name, timeout=0.2):
                pass
        elapsed = time.time() - start_time

        # Should have waited approximately 0.2 seconds
        assert 0.18 <= elapsed <= 0.25

        thread.join()

    def test_lock_reuse_after_release(self) -> None:
        """Test that lock can be reused after release."""
        lock_name = "reuse_test"

        # First acquisition
        with self.lock_manager.acquire(lock_name):
            pass

        # Second acquisition should succeed
        with self.lock_manager.acquire(lock_name):
            pass

        # Third acquisition should also succeed
        with self.lock_manager.acquire(lock_name):
            pass

    def test_different_lock_names(self) -> None:
        """Test that different lock names work independently."""
        results = []

        def acquire_lock(lock_name: str, result_value: str) -> None:
            with self.lock_manager.acquire(lock_name):
                results.append(result_value)
                sleep(0.1)

        # Start threads with different lock names
        thread1 = Thread(target=acquire_lock, args=("lock1", "result1"))
        thread2 = Thread(target=acquire_lock, args=("lock2", "result2"))

        thread1.start()
        thread2.start()

        thread1.join()
        thread2.join()

        # Both should succeed since they have different names
        assert "result1" in results
        assert "result2" in results
        assert len(results) == 2
