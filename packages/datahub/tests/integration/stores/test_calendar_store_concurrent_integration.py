"""
Concurrency tests for CalendarStore.

Tests thread-safety of reload() method using concurrent readers and writers.
"""

import os
import pathlib
import tempfile
import threading
import time

from ditto_datahub.stores.calendar_store import CalendarStore
from ditto_datahub.stores.sqlite_client import SQLiteClient
from ditto_foundation import SQLitePool
from ditto_foundation.cache import DataCache


class TestCalendarStoreConcurrent:
    """Tests for CalendarStore concurrent access."""

    def setup_method(self) -> None:
        """Set up test database."""
        # Use temporary file database for multi-threaded access
        self.db_fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(self.db_fd)  # Close file descriptor

        # Get schema path
        schema_path = (
            pathlib.Path(__file__).parent.parent.parent.parent
            / "src"
            / "ditto_datahub"
            / "scripts"
            / "schema.sql"
        )

        # Initialize pool and schema
        self.pool = SQLitePool(self.db_path, schema_path=schema_path)
        self.pool.init_schema()

        # Create client and store
        self.client = SQLiteClient(self.pool)
        self.store = CalendarStore(self.client)

        # Insert test calendar data
        self._insert_test_data()

    def _insert_test_data(self) -> None:
        """Insert test trading calendar data."""
        # Test data: 2024-01-01 to 2024-01-10
        test_data = [
            (
                "2024-01-01",
                False,
                None,
                "2024-01-02",
                1,
                1,
                1,
                2024,
                False,
                False,
                False,
            ),
            (
                "2024-01-02",
                True,
                None,
                "2024-01-03",
                1,
                1,
                1,
                2024,
                False,
                False,
                False,
            ),
            (
                "2024-01-03",
                True,
                "2024-01-02",
                "2024-01-04",
                1,
                1,
                1,
                2024,
                False,
                False,
                False,
            ),
            (
                "2024-01-04",
                True,
                "2024-01-03",
                "2024-01-05",
                1,
                1,
                1,
                2024,
                False,
                False,
                False,
            ),
            (
                "2024-01-05",
                True,
                "2024-01-04",
                "2024-01-08",
                1,
                1,
                1,
                2024,
                True,
                False,
                False,
            ),
            (
                "2024-01-06",
                False,
                "2024-01-05",
                "2024-01-08",
                1,
                1,
                1,
                2024,
                False,
                False,
                False,
            ),
            (
                "2024-01-07",
                False,
                "2024-01-05",
                "2024-01-08",
                1,
                1,
                1,
                2024,
                False,
                False,
                False,
            ),
            (
                "2024-01-08",
                True,
                "2024-01-05",
                "2024-01-09",
                2,
                1,
                1,
                2024,
                False,
                False,
                False,
            ),
            (
                "2024-01-09",
                True,
                "2024-01-08",
                "2024-01-10",
                2,
                1,
                1,
                2024,
                False,
                False,
                False,
            ),
            (
                "2024-01-10",
                True,
                "2024-01-09",
                None,
                2,
                1,
                1,
                2024,
                False,
                False,
                False,
            ),
        ]

        for row in test_data:
            self.client.execute(
                """INSERT INTO trading_calendar
                (trade_date, is_open, prev_trade_date, next_trade_date,
                 week_of_year, month, quarter, year,
                 is_week_end, is_month_end, is_quarter_end)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                row,
            )

        self.client.execute(
            "UPDATE trading_calendar SET prev_trade_date = NULL WHERE trade_date = ?",
            ["2024-01-02"],
        )
        self.client.execute(
            "UPDATE trading_calendar SET next_trade_date = NULL WHERE trade_date = ?",
            ["2024-01-10"],
        )

        self.client.commit()
        self.store._load_cache()

    def test_reload_thread_safety(self) -> None:
        """
        Test concurrent reload operations for thread safety.

        This test creates multiple reader threads and a reloader thread
        that operate concurrently. It verifies that:
        1. No exceptions are raised during concurrent access
        2. Data consistency is maintained (no empty results)
        3. All operations complete successfully
        """
        errors: list[Exception] = []
        results: list[dict[str, object]] = []

        def reader_thread(thread_id: int) -> None:
            """Simulate concurrent read operations."""
            try:
                for i in range(100):
                    # Perform various read operations
                    is_trading = self.store.is_trading_day("2024-01-02")
                    day = self.store.get("2024-01-03")
                    self.store.get_prev("2024-01-05")
                    self.store.get_next("2024-01-05")
                    self.store.offset("2024-01-02", 2)
                    range_days = self.store.get_range("2024-01-02", "2024-01-10")

                    # Record results for validation
                    if i % 10 == 0:  # Sample 10% of results
                        results.append(
                            {
                                "thread": f"reader-{thread_id}",
                                "is_trading": is_trading,
                                "day_exists": day is not None,
                                "range_len": len(range_days),
                            }
                        )

                    # Small delay to increase chance of race conditions
                    time.sleep(0.0001)

            except Exception as e:
                errors.append(Exception(f"Reader thread {thread_id} failed: {e!s}"))

        def reloader_thread() -> None:
            """Simulate concurrent reload operations."""
            try:
                for _ in range(20):
                    self.store.reload()
                    time.sleep(0.001)  # Small delay between reloads

            except Exception as e:
                errors.append(Exception(f"Reloader thread failed: {e!s}"))

        # Start threads: 10 readers + 1 reloader
        threads = []
        for i in range(10):
            t = threading.Thread(target=reader_thread, args=(i,))
            threads.append(t)

        reloader = threading.Thread(target=reloader_thread)
        threads.append(reloader)

        # Start all threads
        for t in threads:
            t.start()

        # Wait for completion
        for t in threads:
            t.join(timeout=30)  # 30 second timeout

        # Verify no errors occurred
        assert len(errors) == 0, f"Concurrent access errors: {errors}"

        # Verify data consistency
        assert len(results) > 0, "No results recorded"

        for result in results:
            # Basic sanity checks
            assert result["is_trading"] is True, "2024-01-02 should be a trading day"
            assert result["day_exists"] is True, "2024-01-03 should exist"
            assert result["range_len"] == 7, "Range should have 7 trading days"

    def test_reload_with_data_cache_thread_safety(self) -> None:
        """Test concurrent reload with DataCache enabled."""
        data_cache = DataCache(ttl_seconds=300, max_size=1000, enable_metrics=False)
        store_with_cache = CalendarStore(self.client, data_cache=data_cache)

        # Load initial data
        store_with_cache._load_cache()

        errors: list[Exception] = []

        def cache_reader_thread(thread_id: int) -> None:
            """Reader that uses cached range queries."""
            try:
                for _ in range(100):
                    # Range queries use DataCache
                    range_days = store_with_cache.get_range("2024-01-01", "2024-01-10")
                    assert len(range_days) == 7, "Should have 7 trading days"

                    # Single day queries
                    is_trading = store_with_cache.is_trading_day("2024-01-05")
                    assert is_trading is True

                    time.sleep(0.0001)

            except Exception as e:
                errors.append(
                    Exception(f"Cache reader thread {thread_id} failed: {e!s}")
                )

        def cache_reloader_thread() -> None:
            """Reloader that invalidates cache."""
            try:
                for _ in range(20):
                    store_with_cache.reload()
                    time.sleep(0.001)

            except Exception as e:
                errors.append(Exception(f"Cache reloader thread failed: {e!s}"))

        # Start threads
        threads = []
        for i in range(8):
            t = threading.Thread(target=cache_reader_thread, args=(i,))
            threads.append(t)

        reloader = threading.Thread(target=cache_reloader_thread)
        threads.append(reloader)

        for t in threads:
            t.start()

        for t in threads:
            t.join(timeout=30)

        assert len(errors) == 0, f"Concurrent cache errors: {errors}"

    def test_multiple_reloader_threads(self) -> None:
        """Test concurrent reload from multiple threads."""
        errors: list[Exception] = []
        reload_count = [0]  # Use list to share between threads
        lock = threading.Lock()

        def aggressive_reloader_thread(thread_id: int) -> None:
            """Multiple threads reloading simultaneously."""
            try:
                for _ in range(10):
                    self.store.reload()

                    with lock:
                        reload_count[0] += 1

                    time.sleep(0.001)

            except Exception as e:
                errors.append(
                    Exception(f"Aggressive reloader {thread_id} failed: {e!s}")
                )

        def validator_thread() -> None:
            """Validate data consistency during reloads."""
            try:
                for _ in range(100):
                    # Validate critical invariants
                    first = self.store.get_first_trading_day()
                    last = self.store.get_last_trading_day()
                    count = self.store.count_trading_days("2024-01-01", "2024-01-10")

                    # These should never be None or empty if cache is valid
                    assert first is not None, "First trading day should not be None"
                    assert last is not None, "Last trading day should not be None"
                    assert count > 0, "Trading day count should be positive"

                    time.sleep(0.0005)

            except Exception as e:
                errors.append(Exception(f"Validator thread failed: {e!s}"))

        # Start multiple reloaders + validator
        threads = []
        for i in range(5):
            t = threading.Thread(target=aggressive_reloader_thread, args=(i,))
            threads.append(t)

        validator = threading.Thread(target=validator_thread)
        threads.append(validator)

        for t in threads:
            t.start()

        for t in threads:
            t.join(timeout=30)

        assert len(errors) == 0, f"Multiple reloader errors: {errors}"
        assert reload_count[0] == 50, f"Expected 50 reloads, got {reload_count[0]}"

    def teardown_method(self) -> None:
        """Clean up after test."""
        # Clean up temporary database file
        try:
            pathlib.Path(self.db_path).unlink(missing_ok=True)
        except Exception:
            pass
