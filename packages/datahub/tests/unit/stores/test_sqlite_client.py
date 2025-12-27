"""Tests for SQLiteClient."""

from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from ditto_datahub.runtime.sqlite_pool import SQLitePool
from ditto_datahub.stores.sqlite_client import SQLiteClient


class TestSQLiteClient:
    """Test cases for SQLiteClient."""

    def setup_method(self) -> None:
        """Set up test environment."""
        self.temp_dir = TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test.db"
        self.pool = SQLitePool(str(self.db_path))
        self.pool.init_schema()
        self.client = SQLiteClient(self.pool)

    def teardown_method(self) -> None:
        """Clean up test environment."""
        self.pool.close()
        self.temp_dir.cleanup()

    def test_conn_property_returns_connection(self) -> None:
        """Test conn property returns a valid connection."""
        conn = self.client.conn
        assert conn is not None
        assert hasattr(conn, "execute")

    def test_execute_returns_cursor(self) -> None:
        """Test execute method returns cursor."""
        cursor = self.client.execute("SELECT 1")
        assert cursor is not None
        row = cursor.fetchone()
        assert row[0] == 1

    def test_execute_with_params(self) -> None:
        """Test execute method with parameters."""
        cursor = self.client.execute("SELECT ?", [42])
        row = cursor.fetchone()
        assert row[0] == 42

    def test_executemany_executes_multiple(self) -> None:
        """Test executemany method executes multiple statements."""
        self.client.execute("CREATE TABLE test (id INTEGER, value TEXT)")
        self.client.commit()

        params: list[list[Any] | tuple[Any, ...]] = [(1, "a"), (2, "b"), (3, "c")]
        self.client.executemany("INSERT INTO test VALUES (?, ?)", params)
        self.client.commit()

        rows = self.client.fetchall("SELECT * FROM test ORDER BY id")
        assert len(rows) == 3
        assert rows[0]["value"] == "a"

    def test_executescript_executes_multiple_statements(self) -> None:
        """Test executescript method executes multiple SQL statements."""
        script = """
        CREATE TABLE test (id INTEGER PRIMARY KEY, value TEXT);
        INSERT INTO test VALUES (1, 'one');
        INSERT INTO test VALUES (2, 'two');
        """
        self.client.executescript(script)

        rows = self.client.fetchall("SELECT * FROM test ORDER BY id")
        assert len(rows) == 2

    def test_fetchone_returns_single_row(self) -> None:
        """Test fetchone method returns single row or None."""
        # Test with data
        row = self.client.fetchone(
            "SELECT * FROM sid_sequence WHERE asset_class = ?", ["stock"]
        )
        assert row is not None
        assert row["asset_class"] == "stock"

        # Test without data
        row = self.client.fetchone(
            "SELECT * FROM sid_sequence WHERE asset_class = ?", ["invalid"]
        )
        assert row is None

    def test_fetchall_returns_all_rows(self) -> None:
        """Test fetchall method returns all rows."""
        rows = self.client.fetchall("SELECT * FROM sid_sequence ORDER BY asset_class")
        assert len(rows) == 5  # stock, etf, index, bond, future
        assert rows[0]["asset_class"] == "bond"

    def test_fetchval_returns_single_value(self) -> None:
        """Test fetchval method returns first column value."""
        val = self.client.fetchval(
            "SELECT current_max FROM sid_sequence WHERE asset_class = ?", ["stock"]
        )
        assert val == 100_000_000

    def test_fetchval_returns_none_for_no_data(self) -> None:
        """Test fetchval method returns None when no data."""
        val = self.client.fetchval(
            "SELECT current_max FROM sid_sequence WHERE asset_class = ?", ["invalid"]
        )
        assert val is None

    def test_commit_commits_transaction(self) -> None:
        """Test commit method commits transaction."""
        sql = (
            "INSERT INTO security "
            "(sid, symbol, name, exchange, asset_class, list_date) "
            "VALUES (?, ?, ?, ?, ?, ?)"
        )
        params = [99999999, "TEST", "Test", "TEST", "stock", "2024-01-01"]
        self.client.execute(sql, params)
        self.client.commit()

        # New connection should see the data
        row = self.client.fetchone("SELECT * FROM security WHERE sid = ?", [99999999])
        assert row is not None

    def test_rollback_undoes_transaction(self) -> None:
        """Test rollback method undoes transaction."""
        self.client.execute("BEGIN")
        sql = (
            "INSERT INTO security "
            "(sid, symbol, name, exchange, asset_class, list_date) "
            "VALUES (?, ?, ?, ?, ?, ?)"
        )
        params = [99999999, "TEST", "Test", "TEST", "stock", "2024-01-01"]
        self.client.execute(sql, params)
        self.client.rollback()

        row = self.client.fetchone("SELECT * FROM security WHERE sid = ?", [99999999])
        assert row is None

    def test_insert_returning_id(self) -> None:
        """Test insert_returning_id returns lastrowid."""
        sql = (
            "INSERT INTO security "
            "(sid, symbol, name, exchange, asset_class, list_date) "
            "VALUES (?, ?, ?, ?, ?, ?)"
        )
        params = [99999999, "TEST", "Test", "TEST", "stock", "2024-01-01"]
        row_id = self.client.insert_returning_id(sql, params)

        # In SQLite without ROWID alias, this returns the rowid
        assert row_id >= 0

    def test_exists_returns_true_for_existing_data(self) -> None:
        """Test exists method returns True when data exists."""
        result = self.client.exists(
            "SELECT 1 FROM sid_sequence WHERE asset_class = ?", ["stock"]
        )
        assert result is True

    def test_exists_returns_false_for_no_data(self) -> None:
        """Test exists method returns False when no data."""
        result = self.client.exists(
            "SELECT 1 FROM sid_sequence WHERE asset_class = ?", ["invalid"]
        )
        assert result is False

    def test_count_returns_row_count(self) -> None:
        """Test count method returns correct row count."""
        count = self.client.count("sid_sequence")
        assert count == 5

    def test_count_with_where_clause(self) -> None:
        """Test count method with WHERE clause."""
        count = self.client.count("sid_sequence", "asset_class = ?", ["stock"])
        assert count == 1
