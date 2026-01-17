"""Tests for SQLite Pool."""

import sqlite3
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from ditto_datahub.runtime.sqlite_pool import SQLitePool


class TestSQLitePool:
    """Test cases for SQLitePool."""

    def setup_method(self) -> None:
        """Set up test environment."""
        self.temp_dir = TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test.db"

    def teardown_method(self) -> None:
        """Clean up test environment."""
        try:
            if hasattr(self, "pool"):
                self.pool.close()
        except Exception:
            pass
        self.temp_dir.cleanup()

    def test_get_connection_returns_connection(self) -> None:
        """Test get_connection returns a valid connection."""
        self.pool = SQLitePool(str(self.db_path))
        conn = self.pool.get_connection()

        assert conn is not None
        assert hasattr(conn, "execute")

    def test_get_connection_returns_correct_type(self) -> None:
        """Test get_connection returns sqlite3.Connection without runtime cast."""
        self.pool = SQLitePool(str(self.db_path))
        conn = self.pool.get_connection()

        # Verify the returned type is sqlite3.Connection
        # Type should be inferred correctly by pyright without runtime cast
        assert isinstance(conn, sqlite3.Connection)

    def test_get_connection_is_thread_local(self) -> None:
        """Test get_connection returns thread-local connection."""
        self.pool = SQLitePool(str(self.db_path))
        conn1 = self.pool.get_connection()
        conn2 = self.pool.get_connection()

        # Same thread should return same connection
        assert conn1 is conn2

    def test_connection_has_row_factory(self) -> None:
        """Test connection has row_factory set for dict-like access."""
        self.pool = SQLitePool(str(self.db_path))
        conn = self.pool.get_connection()

        # Row factory should be set for sqlite3.Row
        assert conn.row_factory is not None

    def test_init_schema_creates_tables(self) -> None:
        """Test init_schema creates all required tables."""
        self.pool = SQLitePool(str(self.db_path))
        self.pool.init_schema()

        # Check that key tables exist
        tables = self.pool.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()

        table_names = [row["name"] for row in tables]

        # Verify core tables exist
        assert "sid_sequence" in table_names
        assert "security" in table_names
        assert "security_mapping" in table_names
        assert "trading_calendar" in table_names
        assert "dq_issue" in table_names
        assert "freeze_point" in table_names
        assert "price_limit_config" in table_names
        assert "universe" in table_names
        assert "universe_constituent" in table_names

    def test_init_schema_idempotent(self) -> None:
        """Test init_schema can be called multiple times safely."""
        self.pool = SQLitePool(str(self.db_path))
        self.pool.init_schema()
        self.pool.init_schema()  # Should not fail

        # Tables should still exist
        tables = self.pool.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        assert len(tables) > 0

    def test_init_schema_initializes_sid_sequence(self) -> None:
        """Test init_schema initializes SID sequence values."""
        self.pool = SQLitePool(str(self.db_path))
        self.pool.init_schema()

        # Check initial SID sequence values
        rows = self.pool.execute(
            "SELECT * FROM sid_sequence ORDER BY asset_class"
        ).fetchall()

        asset_classes = {row["asset_class"]: row["current_max"] for row in rows}

        assert asset_classes.get("stock") == 1_000_000
        assert asset_classes.get("etf") == 2_000_000
        assert asset_classes.get("index") == 3_000_000
        assert asset_classes.get("bond") == 4_000_000
        assert asset_classes.get("future") == 5_000_000

    def test_execute_method_works(self) -> None:
        """Test execute method works for basic queries."""
        self.pool = SQLitePool(str(self.db_path))
        self.pool.init_schema()

        # Query sid_sequence table
        rows = self.pool.execute("SELECT * FROM sid_sequence").fetchall()
        assert len(rows) == 5  # stock, etf, index, bond, future

    def test_commit_method_works(self) -> None:
        """Test commit method works."""
        self.pool = SQLitePool(str(self.db_path))
        self.pool.init_schema()

        # Insert a test record
        sql = (
            "INSERT INTO security "
            "(sid, symbol, name, exchange, asset_class, list_date) "
            "VALUES (?, ?, ?, ?, ?, ?)"
        )
        params = [99999999, "TEST", "Test Security", "TEST", "stock", "2024-01-01"]
        self.pool.execute(sql, params)
        self.pool.commit()

        # Verify it was committed
        row = self.pool.execute(
            "SELECT * FROM security WHERE sid = ?", [99999999]
        ).fetchone()
        assert row is not None
        assert row["symbol"] == "TEST"

    def test_rollback_method_works(self) -> None:
        """Test rollback method works."""
        self.pool = SQLitePool(str(self.db_path))
        self.pool.init_schema()

        # Begin transaction, insert, rollback
        self.pool.execute("BEGIN")
        sql = (
            "INSERT INTO security "
            "(sid, symbol, name, exchange, asset_class, list_date) "
            "VALUES (?, ?, ?, ?, ?, ?)"
        )
        params = [99999999, "TEST", "Test Security", "TEST", "stock", "2024-01-01"]
        self.pool.execute(sql, params)
        self.pool.rollback()

        # Verify record was not saved
        row = self.pool.execute(
            "SELECT * FROM security WHERE sid = ?", [99999999]
        ).fetchone()
        assert row is None

    def test_close_method_works(self) -> None:
        """Test close method closes connection."""
        self.pool = SQLitePool(str(self.db_path))
        self.pool.init_schema()

        conn = self.pool.get_connection()
        assert conn is not None

        self.pool.close()

        # After close, connection should be reset
        # Note: In thread-local pattern, we can't directly test connection closure
        # but we can verify the pool is still functional with a new connection
        new_conn = self.pool.get_connection()
        assert new_conn is not None

    def test_foreign_key_constraint_enforced(self) -> None:
        """Test that foreign key constraints are enforced."""
        self.pool = SQLitePool(str(self.db_path))
        self.pool.init_schema()

        # Insert a valid security first
        self.pool.execute(
            "INSERT INTO security "
            "(sid, symbol, name, exchange, asset_class, list_date) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            [1000001, "600000", "Test", "SSE", "stock", "2000-01-01"],
        )
        self.pool.commit()

        # Try to insert a mapping with invalid SID (should fail)
        with pytest.raises(sqlite3.IntegrityError):
            self.pool.execute(
                "INSERT INTO security_mapping (sid, source, src_code, effective_from) "
                "VALUES (?, ?, ?, ?)",
                [999999, "tushare", "INVALID", "2000-01-01"],
            )

    def test_foreign_key_constraint_allows_valid_mapping(self) -> None:
        """Test that foreign key constraints allow valid mappings."""
        self.pool = SQLitePool(str(self.db_path))
        self.pool.init_schema()

        # Insert a valid security
        self.pool.execute(
            "INSERT INTO security "
            "(sid, symbol, name, exchange, asset_class, list_date) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            [1000001, "600000", "Test", "SSE", "stock", "2000-01-01"],
        )
        self.pool.commit()

        # Should allow valid mapping
        self.pool.execute(
            "INSERT INTO security_mapping (sid, source, src_code, effective_from) "
            "VALUES (?, ?, ?, ?)",
            [1000001, "tushare", "600000.SH", "2000-01-01"],
        )
        self.pool.commit()

        # Verify it was inserted
        rows = self.pool.execute(
            "SELECT COUNT(*) as count FROM security_mapping WHERE sid = ?",
            [1000001],
        ).fetchall()
        count = rows[0]["count"]
        assert count == 1
