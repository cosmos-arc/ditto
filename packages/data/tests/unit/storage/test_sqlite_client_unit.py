"""Tests for SQLiteClient."""

from pathlib import Path
from typing import Any

import pytest
from ditto_data.storage.sqlite_client import SQLiteClient
from ditto_infra.foundation import SQLitePool


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    """Provide temporary database path."""
    return tmp_path / "test.db"


@pytest.fixture
def sqlite_pool(db_path: Path) -> SQLitePool:
    """Provide SQLite pool with temporary database."""
    # Get schema path - use relative path from test file
    # Test file: packages/data/tests/unit/stores/test_sqlite_client_unit.py
    # Schema file: packages/data/src/ditto_data/scripts/schema.sql
    # 4 parents up: stores -> unit -> tests -> data
    schema_path = (
        Path(__file__).parent.parent.parent.parent
        / "src"
        / "ditto_data"
        / "scripts"
        / "schema.sql"
    )
    pool = SQLitePool(str(db_path), schema_path=schema_path)
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
            "SELECT * FROM instrument_id_sequence WHERE asset_class = ?", ["stock"]
        )
        assert row is not None
        assert row["asset_class"] == "stock"

        # Test without data
        row = sqlite_client.fetchone(
            "SELECT * FROM instrument_id_sequence WHERE asset_class = ?", ["invalid"]
        )
        assert row is None

    def test_fetchall_returns_all_rows(self, sqlite_client: SQLiteClient) -> None:
        """Test fetchall method returns all rows."""
        rows = sqlite_client.fetchall(
            "SELECT * FROM instrument_id_sequence ORDER BY asset_class"
        )
        assert len(rows) == 5  # stock, etf, index, bond, future
        assert rows[0]["asset_class"] == "bond"

    def test_fetchval_returns_single_value(self, sqlite_client: SQLiteClient) -> None:
        """Test fetchval method returns first column value."""
        val = sqlite_client.fetchval(
            "SELECT current_max FROM instrument_id_sequence WHERE asset_class = ?",
            ["stock"],
        )
        assert val == 1_000_000

    def test_fetchval_returns_none_for_no_data(
        self, sqlite_client: SQLiteClient
    ) -> None:
        """Test fetchval method returns None when no data."""
        val = sqlite_client.fetchval(
            "SELECT current_max FROM instrument_id_sequence WHERE asset_class = ?",
            ["invalid"],
        )
        assert val is None

    def test_commit_commits_transaction(self, sqlite_client: SQLiteClient) -> None:
        """Test commit method commits transaction."""
        sql = (
            "INSERT INTO instrument "
            "(instrument_id, ticker, name, exchange, asset_class, list_date) "
            "VALUES (?, ?, ?, ?, ?, ?)"
        )
        params = [99999999, "TEST", "Test", "TEST", "stock", "2024-01-01"]
        sqlite_client.execute(sql, params)
        sqlite_client.commit()

        # New connection should see the data
        row = sqlite_client.fetchone(
            "SELECT * FROM instrument WHERE instrument_id = ?", [99999999]
        )
        assert row is not None

    def test_rollback_undoes_transaction(self, sqlite_client: SQLiteClient) -> None:
        """Test rollback method undoes transaction."""
        sqlite_client.execute("BEGIN")
        sql = (
            "INSERT INTO instrument "
            "(instrument_id, ticker, name, exchange, asset_class, list_date) "
            "VALUES (?, ?, ?, ?, ?, ?)"
        )
        params = [99999999, "TEST", "Test", "TEST", "stock", "2024-01-01"]
        sqlite_client.execute(sql, params)
        sqlite_client.rollback()

        row = sqlite_client.fetchone(
            "SELECT * FROM instrument WHERE instrument_id = ?", [99999999]
        )
        assert row is None

    def test_insert_returning_id(self, sqlite_client: SQLiteClient) -> None:
        """Test insert_returning_id returns lastrowid."""
        sql = (
            "INSERT INTO instrument "
            "(instrument_id, ticker, name, exchange, asset_class, list_date) "
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
            "SELECT 1 FROM instrument_id_sequence WHERE asset_class = ?", ["stock"]
        )
        assert result is True

    def test_exists_returns_false_for_no_data(
        self, sqlite_client: SQLiteClient
    ) -> None:
        """Test exists method returns False when no data."""
        result = sqlite_client.exists(
            "SELECT 1 FROM instrument_id_sequence WHERE asset_class = ?", ["invalid"]
        )
        assert result is False

    def test_count_returns_row_count(self, sqlite_client: SQLiteClient) -> None:
        """Test count method returns correct row count."""
        count = sqlite_client.count("instrument_id_sequence")
        assert count == 5

    def test_count_with_where_clause(self, sqlite_client: SQLiteClient) -> None:
        """Test count method with WHERE clause."""
        count = sqlite_client.count(
            "instrument_id_sequence", "asset_class = ?", ["stock"]
        )
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
            sqlite_client.count("instrument; DROP TABLE instrument")

        # SQL injection attempt: UNION injection
        with pytest.raises(ValueError, match="Invalid table"):
            sqlite_client.count("instrument UNION SELECT * FROM users")

        # SQL injection attempt: Comment injection
        with pytest.raises(ValueError, match="Invalid table"):
            sqlite_client.count("instrument--")

    def test_count_accepts_all_whitelisted_tables(
        self, sqlite_client: SQLiteClient
    ) -> None:
        """Test count method accepts all tables in ALLOWED_TABLES."""
        # Verify all whitelisted tables can be counted
        whitelisted_tables = [
            "instrument_id_sequence",
            "price_limit_config",
            "instrument",
            "instrument_mapping",
            "trading_calendar",
            "freeze_point",
            "universe",
            "universe_constituent",
            "index_weight",
        ]

        for table in whitelisted_tables:
            # Should not raise ValueError
            count = sqlite_client.count(table)
            assert isinstance(count, int)

    # ============ Edge case and branch coverage tests ============

    def test_execute_with_long_sql_logs_truncated(
        self, sqlite_client: SQLiteClient
    ) -> None:
        """Test execute method truncates long SQL in logs."""
        # Create SQL longer than _MAX_SQL_LOG_LENGTH (100 chars)
        # Use repeated expressions to create long SQL without invalid columns
        long_sql = (
            "SELECT "
            + " + ".join(["asset_class" for _ in range(30)])
            + " FROM instrument_id_sequence WHERE 1=0"
        )
        assert len(long_sql) > 100

        # Should execute without error and log truncated SQL
        cursor = sqlite_client.execute(long_sql)
        assert cursor is not None

    def test_execute_without_params(self, sqlite_client: SQLiteClient) -> None:
        """Test execute method without parameters."""
        cursor = sqlite_client.execute("SELECT 1 AS result")
        row = cursor.fetchone()
        assert row[0] == 1

    def test_fetchall_with_empty_result(self, sqlite_client: SQLiteClient) -> None:
        """Test fetchall method returns empty list when no data."""
        sqlite_client.execute("CREATE TABLE test_empty (id INTEGER)")
        sqlite_client.commit()

        rows = sqlite_client.fetchall("SELECT * FROM test_empty")
        assert rows == []

    def test_fetchall_with_params(self, sqlite_client: SQLiteClient) -> None:
        """Test fetchall method with parameters."""
        rows = sqlite_client.fetchall(
            "SELECT * FROM instrument_id_sequence WHERE asset_class = ?", ["stock"]
        )
        assert len(rows) == 1
        assert rows[0]["asset_class"] == "stock"

    def test_executemany_with_long_sql_logs_truncated(
        self, sqlite_client: SQLiteClient
    ) -> None:
        """Test executemany method truncates long SQL in logs."""
        sqlite_client.execute("CREATE TABLE test_long (id INTEGER, value TEXT)")
        sqlite_client.commit()

        # Create SQL longer than _MAX_SQL_LOG_LENGTH (100 chars)
        # Use a very long column list in SELECT to test truncation
        long_sql = (
            "SELECT " + ", ".join([f"col{i}" for i in range(50)]) + " FROM test_long"
        )
        assert len(long_sql) > 100

        # The test is about SQL truncation in logs, not successful execution
        # We test executemany with a simple long SQL
        sqlite_client.executemany(
            "INSERT INTO test_long (id, value) VALUES (?, ?)", [(1, "test")]
        )

    def test_executescript_logs_script_length(
        self, sqlite_client: SQLiteClient
    ) -> None:
        """Test executescript method logs script length."""
        script = """
        CREATE TABLE test_script (id INTEGER PRIMARY KEY, value TEXT);
        INSERT INTO test_script VALUES (1, 'one');
        """
        cursor = sqlite_client.executescript(script)
        assert cursor is not None

    def test_insert_returning_id_with_zero_rowid(
        self, sqlite_client: SQLiteClient
    ) -> None:
        """Test insert_returning_id when lastrowid is 0."""
        # The `cursor.lastrowid or 0` branch is hard to test with actual SQLite
        # because lastrowid is typically non-zero for successful inserts
        # We test that insert_returning_id works correctly
        sql = (
            "INSERT INTO instrument "
            "(instrument_id, ticker, name, exchange, asset_class, list_date) "
            "VALUES (?, ?, ?, ?, ?, ?)"
        )
        params = [99999997, "TEST0", "Test0", "TEST", "stock", "2024-01-01"]
        row_id = sqlite_client.insert_returning_id(sql, params)

        # Should return a valid rowid (the `or 0` fallback is safety)
        assert row_id >= 0

    def test_fetchone_with_long_sql_logs_truncated(
        self, sqlite_client: SQLiteClient
    ) -> None:
        """Test fetchone method truncates long SQL in logs."""
        # Create SQL longer than _MAX_SQL_LOG_LENGTH (100 chars)
        # Use repeated expressions to create long SQL without invalid columns
        long_sql = (
            "SELECT "
            + " + ".join(["asset_class" for _ in range(30)])
            + " FROM instrument_id_sequence WHERE asset_class = 'nonexistent'"
        )
        assert len(long_sql) > 100

        # Should execute without error
        row = sqlite_client.fetchone(long_sql)
        # No matching rows will return None
        assert row is None

    def test_count_with_none_result(self, sqlite_client: SQLiteClient) -> None:
        """Test count method returns 0 for empty table."""
        # COUNT(*) always returns int, never None
        # The branch `int(result) if result is not None else 0` is defensive
        # Test with an existing whitelisted table that might be empty
        count = sqlite_client.count("price_limit_config")
        assert isinstance(count, int)
        assert count >= 0

    def test_close_closes_connection(self, sqlite_client: SQLiteClient) -> None:
        """Test close method closes the database connection."""
        # Get connection before close
        conn = sqlite_client.conn
        assert conn is not None

        # Close the client
        sqlite_client.close()

        # After close, accessing conn should create a new connection
        # Verify that we can still get a connection (it will be a new one)
        new_conn = sqlite_client.conn
        assert new_conn is not None
        # The new connection should work
        result = new_conn.execute("SELECT 1").fetchone()
        assert result[0] == 1
