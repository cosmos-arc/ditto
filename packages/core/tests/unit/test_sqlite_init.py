"""Tests for SQLite database initialization."""

import sqlite3
from pathlib import Path

from ditto_core.data.adapters.sqlite_adapter import SQLiteAdapter


class TestSQLiteInit:
    """Test SQLite database initialization and schema creation."""

    def test_create_database_with_schema(self) -> None:
        """Test that database and schema are created correctly."""
        # Use a test database file
        test_db_path = Path("test_sqlite.db")

        # Clean up any existing test database
        if test_db_path.exists():
            test_db_path.unlink()

        try:
            # Create adapter
            SQLiteAdapter(str(test_db_path))

            # Check that database file was created
            assert test_db_path.exists()

            # Verify schema exists
            conn = sqlite3.connect(str(test_db_path))
            cursor = conn.cursor()

            # Check tables exist
            cursor.execute("""
                SELECT name FROM sqlite_master
                WHERE type='table' AND name IN (
                    'trades', 'orders', 'positions', 'portfolio_snapshots',
                    'strategy_configs', 'execution_logs'
                )
            """)
            tables = {row[0] for row in cursor.fetchall()}

            expected_tables = {
                "trades",
                "orders",
                "positions",
                "portfolio_snapshots",
                "strategy_configs",
                "execution_logs",
            }
            assert tables == expected_tables

            conn.close()

        finally:
            # Clean up
            if test_db_path.exists():
                test_db_path.unlink()

    def test_trades_table_structure(self) -> None:
        """Test that trades table has correct structure."""
        test_db_path = Path("test_sqlite_trades.db")

        if test_db_path.exists():
            test_db_path.unlink()

        try:
            SQLiteAdapter(str(test_db_path))

            conn = sqlite3.connect(str(test_db_path))
            cursor = conn.cursor()

            # Get table info
            cursor.execute("PRAGMA table_info(trades)")
            columns = cursor.fetchall()

            # Convert to more readable format
            column_info = {
                col[1]: {
                    "type": str(col[2]),
                    "not_null": bool(col[3]),
                    "primary_key": bool(col[5]),
                }
                for col in columns
            }

            # Check required columns
            assert "trade_id" in column_info
            assert column_info["trade_id"]["primary_key"]
            assert str(column_info["trade_id"]["type"]).upper() == "INTEGER"

            assert "symbol" in column_info
            assert str(column_info["symbol"]["type"]).upper() == "TEXT"
            assert column_info["symbol"]["not_null"]

            assert "quantity" in column_info
            assert str(column_info["quantity"]["type"]).upper() == "INTEGER"
            assert column_info["quantity"]["not_null"]

            assert "price" in column_info
            assert str(column_info["price"]["type"]).upper() == "REAL"
            assert column_info["price"]["not_null"]

            assert "trade_date" in column_info
            assert str(column_info["trade_date"]["type"]).upper() == "TEXT"
            assert column_info["trade_date"]["not_null"]

            conn.close()

        finally:
            if test_db_path.exists():
                test_db_path.unlink()
