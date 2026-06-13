"""Multi-thread tests for SQLitePool.close_all()."""

import queue
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
        pool.get_connection()
        pool.close_all()

        worker_count = 5
        release_workers = threading.Event()
        worker_results: queue.Queue[int | Exception] = queue.Queue()

        def get_conn_in_thread() -> None:
            try:
                conn = pool.get_connection()
                worker_results.put(id(conn))
                release_workers.wait(timeout=5.0)
            except Exception as exc:
                worker_results.put(exc)

        # Keep worker threads alive after connection creation so close_all()
        # sees the live thread-local connections it is expected to close.
        threads = [
            threading.Thread(target=get_conn_in_thread) for _ in range(worker_count)
        ]
        for t in threads:
            t.start()
        try:
            worker_connection_ids: list[int] = []
            for _ in threads:
                try:
                    result = worker_results.get(timeout=10.0)
                except queue.Empty as exc:
                    raise AssertionError(
                        "timed out waiting for worker SQLite connection"
                    ) from exc

                if isinstance(result, Exception):
                    raise AssertionError(
                        "worker failed to create connection"
                    ) from result
                worker_connection_ids.append(result)

            assert len(worker_connection_ids) == worker_count
            assert len(set(worker_connection_ids)) == worker_count

            # Main thread also gets a connection after workers are concurrently alive.
            main_conn = pool.get_connection()

            # Verify we have 6 distinct connections total (5 workers + main).
            assert id(main_conn) not in worker_connection_ids
            assert pool._connection_count == worker_count + 1

            # Close all connections
            pool.close_all()

            # Verify connection count is reset
            assert pool._connection_count == 0

            # Verify: all connections tracking list is cleared
            assert len(pool._all_connections) == 0
        finally:
            release_workers.set()
            pool.close_all()
            for t in threads:
                t.join(timeout=5.0)

        assert all(not t.is_alive() for t in threads)

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
