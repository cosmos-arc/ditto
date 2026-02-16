"""Unit tests for SQLitePool."""

import sqlite3
import tempfile
from pathlib import Path

import pytest
from ditto_infra.foundation.db import LegacySchemaError, SQLitePool


@pytest.fixture
def temp_db():
    """Create a temporary database file and ensure cleanup."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "test.db"
        pool = SQLitePool(str(db_path))
        yield pool
        # Ensure connection is closed before cleanup
        pool.close()


@pytest.mark.unit
class TestSQLitePoolInitialization:
    """Tests for SQLitePool initialization."""

    def test_init_with_db_path(self) -> None:
        """Test initialization with database path."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "test.db"
            pool = SQLitePool(str(db_path))

            assert pool._db_path == db_path
            assert pool._schema_path is None
            assert pool._connection_count == 0

    def test_init_with_schema_path(self) -> None:
        """Test initialization with schema path."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "test.db"
            schema_path = Path(tmp_dir) / "schema.sql"

            # Create a simple schema file
            schema_path.write_text("CREATE TABLE IF NOT EXISTS test (id INTEGER);")

            pool = SQLitePool(str(db_path), schema_path=schema_path)

            assert pool._db_path == db_path
            assert pool._schema_path == schema_path


@pytest.mark.unit
class TestSQLitePoolConnection:
    """Tests for SQLitePool connection management."""

    def test_get_connection_creates_connection(self) -> None:
        """Test that get_connection creates a new connection."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "test.db"
            pool = SQLitePool(str(db_path))

            conn = pool.get_connection()

            assert conn is not None
            assert isinstance(conn, sqlite3.Connection)

            pool.close()

    def test_get_connection_returns_row_factory(self) -> None:
        """Test that connection has row_factory set to sqlite3.Row."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "test.db"
            pool = SQLitePool(str(db_path))

            conn = pool.get_connection()

            assert conn.row_factory == sqlite3.Row

            pool.close()

    def test_get_connection_enables_foreign_keys(self) -> None:
        """Test that foreign keys are enabled."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "test.db"
            pool = SQLitePool(str(db_path))

            conn = pool.get_connection()
            cursor = conn.execute("PRAGMA foreign_keys;")
            result = cursor.fetchone()

            assert result[0] == 1

            pool.close()

    def test_get_connection_thread_local(self) -> None:
        """Test that connections are thread-local."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "test.db"
            pool = SQLitePool(str(db_path))

            conn1 = pool.get_connection()
            conn2 = pool.get_connection()

            # Same connection for same thread
            assert conn1 is conn2

            pool.close()

    def test_close_connection(self) -> None:
        """Test closing a connection."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "test.db"
            pool = SQLitePool(str(db_path))

            # Create connection
            pool.get_connection()
            assert hasattr(pool._local, "conn")

            # Close connection
            pool.close()
            assert not hasattr(pool._local, "conn")


@pytest.mark.unit
class TestSQLitePoolExecute:
    """Tests for SQLitePool execute method."""

    def test_execute_select_query(self) -> None:
        """Test executing a SELECT query."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "test.db"
            pool = SQLitePool(str(db_path))

            # Create a test table
            pool.execute("CREATE TABLE test (id INTEGER, name TEXT)")
            pool.execute("INSERT INTO test VALUES (1, 'Alice')")
            pool.commit()

            # Execute query
            cursor = pool.execute("SELECT * FROM test WHERE id = ?", [1])
            result = cursor.fetchone()

            assert result["id"] == 1
            assert result["name"] == "Alice"

            pool.close()

    def test_execute_with_params(self) -> None:
        """Test execute with parameters."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "test.db"
            pool = SQLitePool(str(db_path))

            pool.execute("CREATE TABLE test (id INTEGER, value TEXT)")
            pool.execute("INSERT INTO test VALUES (?, ?)", [1, "test"])
            pool.commit()

            cursor = pool.execute("SELECT value FROM test WHERE id = ?", [1])
            result = cursor.fetchone()

            assert result["value"] == "test"

            pool.close()

    def test_execute_without_params(self) -> None:
        """Test execute without parameters."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "test.db"
            pool = SQLitePool(str(db_path))

            cursor = pool.execute("SELECT 1 AS result")
            result = cursor.fetchone()

            assert result["result"] == 1

            pool.close()


@pytest.mark.unit
class TestSQLitePoolTransactions:
    """Tests for SQLitePool transaction management."""

    def test_commit_transaction(self) -> None:
        """Test committing a transaction."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "test.db"
            pool = SQLitePool(str(db_path))

            pool.execute("CREATE TABLE test (id INTEGER)")
            pool.execute("INSERT INTO test VALUES (1)")
            pool.commit()

            cursor = pool.execute("SELECT COUNT(*) as count FROM test")
            result = cursor.fetchone()

            assert result["count"] == 1

            pool.close()

    def test_rollback_transaction(self) -> None:
        """Test rolling back a transaction."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "test.db"
            pool = SQLitePool(str(db_path))

            pool.execute("CREATE TABLE test (id INTEGER)")
            pool.execute("INSERT INTO test VALUES (1)")
            pool.rollback()

            cursor = pool.execute("SELECT COUNT(*) as count FROM test")
            result = cursor.fetchone()

            # Rollback doesn't undo changes in auto-commit mode
            # SQLite default is auto-commit
            assert result["count"] == 0

            pool.close()


@pytest.mark.unit
class TestSQLitePoolSchema:
    """Tests for SQLitePool schema initialization."""

    def test_init_schema_without_path(self) -> None:
        """Test init_schema when no schema_path is provided."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "test.db"
            pool = SQLitePool(str(db_path))

            # Should not raise, just log warning
            pool.init_schema()

            pool.close()

    def test_init_schema_from_file(self) -> None:
        """Test init_schema reads and executes schema file."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "test.db"
            schema_path = Path(tmp_dir) / "schema.sql"

            # Create schema file
            schema_path.write_text(
                "CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT);"
            )

            pool = SQLitePool(str(db_path), schema_path=schema_path)
            pool.init_schema()

            # Verify table was created
            cursor = pool.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='users'"
            )
            result = cursor.fetchone()

            assert result is not None
            assert result["name"] == "users"

            pool.close()

    def test_init_schema_empty_file(self) -> None:
        """Test init_schema with empty schema file."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "test.db"
            schema_path = Path(tmp_dir) / "schema.sql"

            # Create empty schema file
            schema_path.write_text("")

            pool = SQLitePool(str(db_path), schema_path=schema_path)

            # Should not raise
            pool.init_schema()

            pool.close()

    def test_init_schema_missing_file(self) -> None:
        """Test init_schema when schema file doesn't exist."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "test.db"
            schema_path = Path(tmp_dir) / "nonexistent.sql"

            pool = SQLitePool(str(db_path), schema_path=schema_path)

            with pytest.raises(ValueError, match="Schema file does not exist"):
                pool.init_schema()

            pool.close()


@pytest.mark.unit
class TestSQLitePoolPing:
    """Tests for SQLitePool ping method."""

    def test_ping_returns_true_for_valid_connection(self) -> None:
        """Test ping returns True for valid connection."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "test.db"
            pool = SQLitePool(str(db_path))

            assert pool.ping() is True

            pool.close()

    def test_ping_returns_false_for_invalid_connection(self) -> None:
        """Test ping returns False when connection fails."""
        # Use invalid path
        pool = SQLitePool("/nonexistent/path/to/db.db")

        assert pool.ping() is False


@pytest.mark.unit
class TestSQLitePoolClose:
    """Tests for SQLitePool close method."""

    def test_close_reduces_connection_count(self) -> None:
        """Test that close reduces connection count."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "test.db"
            pool = SQLitePool(str(db_path))

            # Create connection
            pool.get_connection()
            initial_count = pool._connection_count
            assert initial_count > 0

            # Close connection
            pool.close()
            assert pool._connection_count == initial_count - 1

            # Second close is safe
            pool.close()

    def test_close_when_no_connection(self) -> None:
        """Test close when no connection exists."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "test.db"
            pool = SQLitePool(str(db_path))

            # Should not raise
            pool.close()
            pool.close()


@pytest.mark.unit
class TestSQLitePoolExceptionPaths:
    """Tests for SQLitePool exception handling."""

    def test_get_connection_with_invalid_path(self) -> None:
        """Test get_connection raises error with invalid database path."""
        # Use a path that cannot be created (non-existent directory with no permissions)
        pool = SQLitePool("/root/nonexistent/path/test.db")

        # OSError or PermissionError expected for invalid path
        with pytest.raises(Exception):  # noqa: B017  # OSError, PermissionError
            pool.get_connection()

    def test_init_schema_with_invalid_sql_content(self, tmp_path: Path) -> None:
        """Test init_schema raises error with invalid SQL content."""
        db_path = tmp_path / "test.db"
        schema_path = tmp_path / "schema.sql"

        # Create invalid SQL file
        schema_path.write_text("INVALID SQL SYNTAX HERE")

        pool = SQLitePool(str(db_path), schema_path=schema_path)

        # sqlite3.DatabaseError expected for invalid SQL
        with pytest.raises(Exception):  # noqa: B017  # sqlite3.DatabaseError
            pool.init_schema()

        pool.close()

    def test_execute_with_invalid_sql(self, tmp_path: Path) -> None:
        """Test execute raises error with invalid SQL."""
        db_path = tmp_path / "test.db"
        pool = SQLitePool(str(db_path))

        with pool.get_connection() as conn:
            # sqlite3.OperationalError expected for invalid SQL
            with pytest.raises(Exception):  # noqa: B017  # sqlite3.OperationalError
                conn.execute("INVALID SQL QUERY")

        pool.close()

    def test_execute_fetchone_with_connection_closed(self, tmp_path: Path) -> None:
        """Test execute/fetchone raises error when connection is closed."""
        db_path = tmp_path / "test.db"
        pool = SQLitePool(str(db_path))

        conn = pool.get_connection()
        pool.close()  # Close the pool

        # ProgrammingError expected for closed connection
        with pytest.raises(Exception):  # noqa: B017  # sqlite3.ProgrammingError
            conn.execute("SELECT 1")

        # Pool is already closed, but safe to call again
        pool.close()

    def test_multiple_connections_exhaust_pool(self, tmp_path: Path) -> None:
        """Test behavior when creating multiple connections."""
        db_path = tmp_path / "test.db"
        pool = SQLitePool(str(db_path))

        # Get first connection
        conn1 = pool.get_connection()
        initial_count = pool._connection_count
        assert initial_count == 1

        # Second call returns same connection (thread-local)
        conn2 = pool.get_connection()
        assert pool._connection_count == 1  # No new connection created

        # Verify same connection
        assert conn1 is conn2

        # Cleanup
        pool.close()
        # Note: thread-local connections persist until thread ends


@pytest.mark.unit
class TestLegacySchemaProtection:
    """Tests for legacy schema protection (ENG-004)."""

    LEGACY_SCHEMA = """
        CREATE TABLE instrument (
            id INTEGER PRIMARY KEY,
            old_column TEXT
        );
        CREATE TABLE instrument_mapping (
            id INTEGER PRIMARY KEY,
            instrument_id INTEGER
        );
    """

    VALID_SCHEMA = """
        CREATE TABLE IF NOT EXISTS instrument (
            instrument_id TEXT PRIMARY KEY,
            ticker TEXT NOT NULL,
            asset_class TEXT NOT NULL,
            exchange TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS instrument_mapping (
            instrument_id TEXT NOT NULL,
            source TEXT NOT NULL,
            source_ticker TEXT NOT NULL,
            PRIMARY KEY (instrument_id, source, source_ticker)
        );
    """

    def test_init_schema_raises_error_on_legacy_without_env(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test LegacySchemaError is raised on legacy schema without env var."""

        monkeypatch.delenv("DITTO_ALLOW_SCHEMA_REBUILD", raising=False)

        db_path = tmp_path / "test.db"
        schema_path = tmp_path / "schema.sql"
        schema_path.write_text(self.VALID_SCHEMA)

        pool = SQLitePool(str(db_path), schema_path=schema_path)

        # Create legacy tables
        conn = pool.get_connection()
        conn.executescript(self.LEGACY_SCHEMA)
        conn.commit()
        pool.close()

        # Reopen pool and try to init_schema
        pool2 = SQLitePool(str(db_path), schema_path=schema_path)

        with pytest.raises(LegacySchemaError, match="Legacy schema detected"):
            pool2.init_schema()

        pool2.close()

    def test_init_schema_rebuilds_with_env_var(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test that init_schema rebuilds legacy schema when env var is set."""
        monkeypatch.setenv("DITTO_ALLOW_SCHEMA_REBUILD", "1")

        db_path = tmp_path / "test.db"
        schema_path = tmp_path / "schema.sql"
        schema_path.write_text(self.VALID_SCHEMA)

        pool = SQLitePool(str(db_path), schema_path=schema_path)

        # Create legacy tables
        conn = pool.get_connection()
        conn.executescript(self.LEGACY_SCHEMA)
        conn.commit()
        pool.close()

        # Reopen pool and init_schema with env var set
        pool2 = SQLitePool(str(db_path), schema_path=schema_path)
        pool2.init_schema()  # Should not raise

        # Verify new schema is applied
        cursor = pool2.execute("PRAGMA table_info(instrument)")
        columns = {row[1] for row in cursor.fetchall()}
        assert "instrument_id" in columns
        assert "ticker" in columns

        pool2.close()

    def test_init_schema_no_rebuild_needed(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test that init_schema works when schema is already valid."""
        monkeypatch.delenv("DITTO_ALLOW_SCHEMA_REBUILD", raising=False)

        db_path = tmp_path / "test.db"
        schema_path = tmp_path / "schema.sql"
        schema_path.write_text(self.VALID_SCHEMA)

        pool = SQLitePool(str(db_path), schema_path=schema_path)
        pool.init_schema()  # First init creates tables
        pool.close()

        # Second init should not raise
        pool2 = SQLitePool(str(db_path), schema_path=schema_path)
        pool2.init_schema()  # Should not raise

        pool2.close()

    def test_init_schema_empty_db_no_rebuild_needed(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test that init_schema works on empty database without env var."""
        monkeypatch.delenv("DITTO_ALLOW_SCHEMA_REBUILD", raising=False)

        db_path = tmp_path / "test.db"
        schema_path = tmp_path / "schema.sql"
        schema_path.write_text(self.VALID_SCHEMA)

        pool = SQLitePool(str(db_path), schema_path=schema_path)
        pool.init_schema()  # Should not raise on empty DB

        pool.close()
