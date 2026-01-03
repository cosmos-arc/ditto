"""Tests for SQLiteClient."""

from pathlib import Path
from typing import Any

import pytest
from ditto_datahub.runtime.sqlite_pool import SQLitePool
from ditto_datahub.stores.sqlite_client import SQLiteClient


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    """Provide temporary database path."""
    return tmp_path / "test.db"


@pytest.fixture
def sqlite_pool(db_path: Path) -> SQLitePool:
    """Provide SQLite pool with temporary database."""
    pool = SQLitePool(str(db_path))
    pool.init_schema()
    yield pool
    pool.close()


@pytest.fixture
def sqlite_client(sqlite_pool: SQLitePool) -> SQLiteClient:
    """Provide SQLite client with temporary database."""
    return SQLiteClient(sqlite_pool)


class TestSQLiteClient:
    """Test cases for SQLiteClient."""

    def test_conn_property_returns_connection(
        self, sqlite_client: SQLiteClient
    ) -> None:
        """Test conn property returns a valid connection."""
        conn = sqlite_client.conn
        assert conn is not None
        assert hasattr(conn, "execute")

    def test_execute_returns_cursor(self, sqlite_client: SQLiteClient) -> None:
        """Test execute method returns cursor."""
        cursor = sqlite_client.execute("SELECT 1")
        assert cursor is not None
        row = cursor.fetchone()
        assert row[0] == 1

    def test_execute_with_params(self, sqlite_client: SQLiteClient) -> None:
        """Test execute method with parameters."""
        cursor = sqlite_client.execute("SELECT ?", [42])
        row = cursor.fetchone()
        assert row[0] == 42

    def test_executemany_executes_multiple(self, sqlite_client: SQLiteClient) -> None:
        """Test executemany method executes multiple statements."""
        sqlite_client.execute("CREATE TABLE test (id INTEGER, value TEXT)")
        sqlite_client.commit()

        params: list[list[Any] | tuple[Any, ...]] = [(1, "a"), (2, "b"), (3, "c")]
        sqlite_client.executemany("INSERT INTO test VALUES (?, ?)", params)
        sqlite_client.commit()

        rows = sqlite_client.fetchall("SELECT * FROM test ORDER BY id")
        assert len(rows) == 3
        assert rows[0]["value"] == "a"

    def test_executescript_executes_multiple_statements(
        self, sqlite_client: SQLiteClient
    ) -> None:
        """Test executescript method executes multiple SQL statements."""
        script = """
        CREATE TABLE test (id INTEGER PRIMARY KEY, value TEXT);
        INSERT INTO test VALUES (1, 'one');
        INSERT INTO test VALUES (2, 'two');
        """
        sqlite_client.executescript(script)

        rows = sqlite_client.fetchall("SELECT * FROM test ORDER BY id")
        assert len(rows) == 2

    def test_fetchone_returns_single_row(self, sqlite_client: SQLiteClient) -> None:
        """Test fetchone method returns single row or None."""
        # Test with data
        row = sqlite_client.fetchone(
            "SELECT * FROM sid_sequence WHERE asset_class = ?", ["stock"]
        )
        assert row is not None
        assert row["asset_class"] == "stock"

        # Test without data
        row = sqlite_client.fetchone(
            "SELECT * FROM sid_sequence WHERE asset_class = ?", ["invalid"]
        )
        assert row is None

    def test_fetchall_returns_all_rows(self, sqlite_client: SQLiteClient) -> None:
        """Test fetchall method returns all rows."""
        rows = sqlite_client.fetchall("SELECT * FROM sid_sequence ORDER BY asset_class")
        assert len(rows) == 5  # stock, etf, index, bond, future
        assert rows[0]["asset_class"] == "bond"

    def test_fetchval_returns_single_value(self, sqlite_client: SQLiteClient) -> None:
        """Test fetchval method returns first column value."""
        val = sqlite_client.fetchval(
            "SELECT current_max FROM sid_sequence WHERE asset_class = ?", ["stock"]
        )
        assert val == 100_000_000

    def test_fetchval_returns_none_for_no_data(
        self, sqlite_client: SQLiteClient
    ) -> None:
        """Test fetchval method returns None when no data."""
        val = sqlite_client.fetchval(
            "SELECT current_max FROM sid_sequence WHERE asset_class = ?", ["invalid"]
        )
        assert val is None

    def test_commit_commits_transaction(self, sqlite_client: SQLiteClient) -> None:
        """Test commit method commits transaction."""
        sql = (
            "INSERT INTO security "
            "(sid, symbol, name, exchange, asset_class, list_date) "
            "VALUES (?, ?, ?, ?, ?, ?)"
        )
        params = [99999999, "TEST", "Test", "TEST", "stock", "2024-01-01"]
        sqlite_client.execute(sql, params)
        sqlite_client.commit()

        # New connection should see the data
        row = sqlite_client.fetchone("SELECT * FROM security WHERE sid = ?", [99999999])
        assert row is not None

    def test_rollback_undoes_transaction(self, sqlite_client: SQLiteClient) -> None:
        """Test rollback method undoes transaction."""
        sqlite_client.execute("BEGIN")
        sql = (
            "INSERT INTO security "
            "(sid, symbol, name, exchange, asset_class, list_date) "
            "VALUES (?, ?, ?, ?, ?, ?)"
        )
        params = [99999999, "TEST", "Test", "TEST", "stock", "2024-01-01"]
        sqlite_client.execute(sql, params)
        sqlite_client.rollback()

        row = sqlite_client.fetchone("SELECT * FROM security WHERE sid = ?", [99999999])
        assert row is None

    def test_insert_returning_id(self, sqlite_client: SQLiteClient) -> None:
        """Test insert_returning_id returns lastrowid."""
        sql = (
            "INSERT INTO security "
            "(sid, symbol, name, exchange, asset_class, list_date) "
            "VALUES (?, ?, ?, ?, ?, ?)"
        )
        params = [99999999, "TEST", "Test", "TEST", "stock", "2024-01-01"]
        row_id = sqlite_client.insert_returning_id(sql, params)

        # In SQLite without ROWID alias, this returns the rowid
        assert row_id >= 0

    def test_exists_returns_true_for_existing_data(
        self, sqlite_client: SQLiteClient
    ) -> None:
        """Test exists method returns True when data exists."""
        result = sqlite_client.exists(
            "SELECT 1 FROM sid_sequence WHERE asset_class = ?", ["stock"]
        )
        assert result is True

    def test_exists_returns_false_for_no_data(
        self, sqlite_client: SQLiteClient
    ) -> None:
        """Test exists method returns False when no data."""
        result = sqlite_client.exists(
            "SELECT 1 FROM sid_sequence WHERE asset_class = ?", ["invalid"]
        )
        assert result is False

    def test_count_returns_row_count(self, sqlite_client: SQLiteClient) -> None:
        """Test count method returns correct row count."""
        count = sqlite_client.count("sid_sequence")
        assert count == 5

    def test_count_with_where_clause(self, sqlite_client: SQLiteClient) -> None:
        """Test count method with WHERE clause."""
        count = sqlite_client.count("sid_sequence", "asset_class = ?", ["stock"])
        assert count == 1

    # ============ Security/Whitelist tests ============

    def test_count_rejects_invalid_table(self, sqlite_client: SQLiteClient) -> None:
        """Test count method rejects tables not in whitelist."""
        with pytest.raises(ValueError, match="Invalid table"):
            sqlite_client.count("malicious_table")

    def test_count_rejects_sql_injection_in_table_name(
        self, sqlite_client: SQLiteClient
    ) -> None:
        """Test count method rejects SQL injection in table name."""
        # SQL injection attempt: DROP TABLE statement
        with pytest.raises(ValueError, match="Invalid table"):
            sqlite_client.count("security; DROP TABLE security")

        # SQL injection attempt: UNION injection
        with pytest.raises(ValueError, match="Invalid table"):
            sqlite_client.count("security UNION SELECT * FROM users")

        # SQL injection attempt: Comment injection
        with pytest.raises(ValueError, match="Invalid table"):
            sqlite_client.count("security--")

    def test_count_accepts_all_whitelisted_tables(
        self, sqlite_client: SQLiteClient
    ) -> None:
        """Test count method accepts all tables in ALLOWED_TABLES."""
        # Verify all whitelisted tables can be counted
        whitelisted_tables = [
            "sid_sequence",
            "price_limit_config",
            "security",
            "security_mapping",
            "trading_calendar",
            "pipeline_run",
            "dq_issue",
            "freeze_point",
            "universe",
            "universe_constituent",
            "index_weight",
        ]

        for table in whitelisted_tables:
            # Should not raise ValueError
            count = sqlite_client.count(table)
            assert isinstance(count, int)
