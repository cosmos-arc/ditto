"""Concurrency tests for IngestionLogStore.

Tests thread-safety of save_log() method using atomic UPSERT.
Validates that attempts counter increments correctly under concurrent access.
"""

import os
import pathlib
import tempfile
import threading

import pytest
from ditto_datahub.runtime.sqlite_pool import SQLitePool
from ditto_datahub.sources.metadata import IngestionLog, IngestionStatus
from ditto_datahub.stores.ingestion_log import IngestionLogStore
from ditto_datahub.stores.sqlite_client import SQLiteClient


@pytest.mark.pit
class TestIngestionLogConcurrent:
    """Tests for IngestionLogStore concurrent access.

    PIT (Pipeline Integration Tests) - tests complete data ingestion flow.
    These tests require more resources and time than unit tests.
    """

    def setup_method(self) -> None:
        """Set up test database."""
        # Use temporary file database for multi-threaded access
        self.db_fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(self.db_fd)  # Close file descriptor

        # Initialize pool and store
        self.pool = SQLitePool(self.db_path)
        self.pool.init_schema()
        self.client = SQLiteClient(self.pool)
        self.store = IngestionLogStore(self.client)

    def test_concurrent_save_log_attempts_increment(self) -> None:
        """Test concurrent save_log increments attempts atomically.

        This test creates multiple threads that all try to save the same log
        record concurrently. It verifies that:
        1. The attempts counter is incremented atomically
        2. No PRIMARY KEY conflicts occur
        3. No data is lost
        """
        base_log = IngestionLog(
            dataset="test_dataset",
            source="tushare",
            trade_date="2024-01-01",
            status=IngestionStatus.SUCCESS,
            checksum="abc123",
            rows=100,
        )

        errors: list[Exception] = []

        def save_in_thread(thread_id: int) -> None:
            """Save log in thread."""
            try:
                self.store.save_log(base_log)
            except Exception as e:
                errors.append(Exception(f"Thread {thread_id} failed: {e!s}"))

        # Start 10 concurrent threads
        threads = []
        for i in range(10):
            t = threading.Thread(target=save_in_thread, args=(i,))
            threads.append(t)
            t.start()

        # Wait for all threads to complete
        for t in threads:
            t.join(timeout=10)

        # Verify no errors occurred
        assert len(errors) == 0, f"Concurrent save errors: {errors}"

        # Verify: attempts should be exactly 10
        final_log = self.store.get_log("test_dataset", "tushare", "2024-01-01")
        assert final_log is not None, "Log should exist"
        assert final_log.attempts == 10, (
            f"Expected attempts=10, got {final_log.attempts}"
        )
        assert final_log.first_attempt_at is not None, "first_attempt_at should be set"
        assert final_log.last_attempt_at is not None, "last_attempt_at should be set"

    def test_concurrent_save_log_different_dates(self) -> None:
        """Test concurrent saves for different dates don't interfere.

        This test verifies that concurrent saves for different trade dates
        don't cause any cross-interference or race conditions.
        """
        errors: list[Exception] = []

        def save_date_range(thread_id: int, start: int, count: int) -> None:
            """Save multiple logs in thread."""
            try:
                for i in range(start, start + count):
                    self.store.save_log(
                        IngestionLog(
                            dataset="test_dataset",
                            source="tushare",
                            trade_date=f"2024-01-{i:02d}",
                            status=IngestionStatus.SUCCESS,
                            checksum=f"checksum_{i}",
                            rows=100 + i,
                        )
                    )
            except Exception as e:
                errors.append(Exception(f"Thread {thread_id} failed: {e!s}"))

        # Start 3 threads, each saving different date ranges
        threads = []
        threads.append(threading.Thread(target=save_date_range, args=(1, 1, 5)))
        threads.append(threading.Thread(target=save_date_range, args=(2, 6, 5)))
        threads.append(threading.Thread(target=save_date_range, args=(3, 11, 5)))

        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert len(errors) == 0, f"Concurrent save errors: {errors}"

        # Verify all 15 records were saved
        all_dates = self.store.get_ingested_dates("test_dataset", "tushare")
        assert len(all_dates) == 15, f"Expected 15 records, got {len(all_dates)}"

        # Verify each record has attempts=1 (no conflicts)
        for date in all_dates:
            log = self.store.get_log("test_dataset", "tushare", date)
            assert log.attempts == 1, f"Date {date} should have attempts=1"

    def test_concurrent_save_then_update(self) -> None:
        """Test concurrent save followed by updates.

        This test simulates a scenario where one thread creates a record
        and multiple threads try to update it concurrently.
        """
        errors: list[Exception] = []

        # Thread 1: Create initial record
        def create_record() -> None:
            try:
                self.store.save_log(
                    IngestionLog(
                        dataset="test_dataset",
                        source="tushare",
                        trade_date="2024-01-01",
                        status=IngestionStatus.FAIL,
                        error_code="ERROR_1",
                    )
                )
            except Exception as e:
                errors.append(Exception(f"Create thread failed: {e!s}"))

        # Threads 2-10: Update the record
        def update_record(thread_id: int) -> None:
            try:
                self.store.save_log(
                    IngestionLog(
                        dataset="test_dataset",
                        source="tushare",
                        trade_date="2024-01-01",
                        status=IngestionStatus.SUCCESS,
                        checksum=f"checksum_{thread_id}",
                        rows=100 + thread_id,
                    )
                )
            except Exception as e:
                errors.append(Exception(f"Update thread {thread_id} failed: {e!s}"))

        # Start create thread first
        create_thread = threading.Thread(target=create_record)
        create_thread.start()
        create_thread.join(timeout=5)

        # Then start multiple update threads concurrently
        update_threads = []
        for i in range(9):
            t = threading.Thread(target=update_record, args=(i + 1,))
            update_threads.append(t)
            t.start()

        for t in update_threads:
            t.join(timeout=10)

        assert len(errors) == 0, f"Concurrent update errors: {errors}"

        # Verify: attempts should be 10 (1 create + 9 updates)
        final_log = self.store.get_log("test_dataset", "tushare", "2024-01-01")
        assert final_log is not None
        assert final_log.attempts == 10, (
            f"Expected attempts=10, got {final_log.attempts}"
        )
        assert final_log.status == IngestionStatus.SUCCESS

    def test_concurrent_mixed_operations(self) -> None:
        """Test concurrent mixed operations (save, get, query).

        This test verifies that concurrent reads and writes don't cause issues.
        """
        errors: list[Exception] = []

        def writer_thread(thread_id: int) -> None:
            """Writer thread saves logs."""
            try:
                for i in range(10):
                    self.store.save_log(
                        IngestionLog(
                            dataset="test_dataset",
                            source="tushare",
                            trade_date=f"2024-01-{thread_id * 10 + i:02d}",
                            status=IngestionStatus.SUCCESS,
                            checksum=f"checksum_{thread_id}_{i}",
                            rows=100,
                        )
                    )
            except Exception as e:
                errors.append(Exception(f"Writer thread {thread_id} failed: {e!s}"))

        def reader_thread(thread_id: int) -> None:
            """Reader thread performs queries."""
            try:
                for _ in range(20):
                    # Various read operations
                    self.store.get_stats("test_dataset", "tushare")
                    self.store.get_ingested_dates("test_dataset", "tushare")
                    self.store.get_failed_dates("test_dataset", "tushare")
            except Exception as e:
                errors.append(Exception(f"Reader thread {thread_id} failed: {e!s}"))

        # Start 5 writer threads
        threads = []
        for i in range(5):
            t = threading.Thread(target=writer_thread, args=(i,))
            threads.append(t)

        # Start 5 reader threads
        for i in range(5):
            t = threading.Thread(target=reader_thread, args=(i,))
            threads.append(t)

        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        assert len(errors) == 0, f"Concurrent operation errors: {errors}"

        # Verify all writes succeeded
        all_dates = self.store.get_ingested_dates("test_dataset", "tushare")
        assert len(all_dates) == 50, f"Expected 50 records, got {len(all_dates)}"

    def teardown_method(self) -> None:
        """Clean up after test."""
        # Clean up temporary database file
        try:
            pathlib.Path(self.db_path).unlink(missing_ok=True)
        except Exception:  # noqa: S110 - cleanup should not raise
            pass
