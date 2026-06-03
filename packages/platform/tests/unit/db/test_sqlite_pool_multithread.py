"""Multi-thread tests for SQLitePool.close_all()."""

import threading
from pathlib import Path

import pytest
from ditto_platform.foundation.db import SQLitePool


@pytest.mark.unit
@pytest.mark.serial
class TestSQLitePoolCloseAll:
    """Tests for SQLitePool.close_all method."""

    def test_close_all_closes_all_thread_connections(self, tmp_path: Path) -> None:
        """close_all should close connections from all threads."""
        db_path = tmp_path / "test.db"
        pool = SQLitePool(str(db_path))

        connections_created: list[int] = []
        connections_created_lock = threading.Lock()

        def get_conn_in_thread() -> None:
            pool.get_connection()
            with connections_created_lock:
                connections_created.append(threading.get_ident())

        # Create connections in 5 separate threads
        threads = [threading.Thread(target=get_conn_in_thread) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Main thread also gets a connection
        pool.get_connection()

        # Verify we have 6 connections total (5 threads + main)
        assert pool._connection_count == 6

        # Close all connections
        pool.close_all()

        # Verify connection count is reset
        assert pool._connection_count == 0

        # Verify: all connections tracking list is cleared
        assert len(pool._all_connections) == 0

    def test_close_all_allows_reconnecting_after_close(self, tmp_path: Path) -> None:
        """After close_all, new connections can be created."""
        db_path = tmp_path / "test.db"
        pool = SQLitePool(str(db_path))

        # Create a connection
        pool.get_connection()
        assert pool._connection_count == 1

        # Close all
        pool.close_all()
        assert pool._connection_count == 0

        # Should be able to get a new connection
        pool.get_connection()
        assert pool._connection_count == 1

        # Cleanup
        pool.close_all()

    def test_close_all_when_no_connections(self, tmp_path: Path) -> None:
        """close_all should be safe when no connections exist."""
        db_path = tmp_path / "test.db"
        pool = SQLitePool(str(db_path))

        # Should not raise when no connections
        pool.close_all()
        assert pool._connection_count == 0

    def test_close_all_idempotent(self, tmp_path: Path) -> None:
        """Calling close_all multiple times should be safe."""
        db_path = tmp_path / "test.db"
        pool = SQLitePool(str(db_path))

        pool.get_connection()
        pool.close_all()
        pool.close_all()  # Second call should not raise
        assert pool._connection_count == 0

    def test_close_all_handles_closed_connections_gracefully(
        self, tmp_path: Path
    ) -> None:
        """close_all should handle already-closed connections without error."""
        db_path = tmp_path / "test.db"
        pool = SQLitePool(str(db_path))

        # Get a connection
        pool.get_connection()

        # Manually close it (simulate external close)
        conn = pool._local.conn
        conn.close()

        # close_all should still work without raising
        pool.close_all()
        assert pool._connection_count == 0
