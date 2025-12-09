"""Tests for DuckDB database initialization."""

from pathlib import Path

import duckdb

from data.adapters.duckdb_adapter import DuckDBAdapter


class TestDuckDBInit:
    """Test DuckDB database initialization and schema creation."""

    def test_create_database_with_schema(self) -> None:
        """Test that database and schema are created correctly."""
        # Use a test database file
        test_db_path = Path("test_duckdb.db")

        # Clean up any existing test database
        if test_db_path.exists():
            test_db_path.unlink()

        try:
            # Create adapter
            DuckDBAdapter(str(test_db_path))

            # Check that database file was created
            assert test_db_path.exists()

            # Verify schema exists
            with duckdb.connect(str(test_db_path)) as conn:
                # Check ETF info table
                result = conn.execute("""
                    SELECT COUNT(*) FROM information_schema.tables
                    WHERE table_name = 'etf_info'
                """).fetchone()
                assert result is not None, "etf_info table should exist"
                assert result[0] == 1, "etf_info table should exist"

                # Check daily price table
                result = conn.execute("""
                    SELECT COUNT(*) FROM information_schema.tables
                    WHERE table_name = 'daily_price'
                """).fetchone()
                assert result is not None, "daily_price table should exist"
                assert result[0] == 1, "daily_price table should exist"

                # Check adjustment factors table
                result = conn.execute("""
                    SELECT COUNT(*) FROM information_schema.tables
                    WHERE table_name = 'adjustment_factors'
                """).fetchone()
                assert result is not None, "adjustment_factors table should exist"
                assert result[0] == 1, "adjustment_factors table should exist"

                # Check trading calendar table
                result = conn.execute("""
                    SELECT COUNT(*) FROM information_schema.tables
                    WHERE table_name = 'trading_calendar'
                """).fetchone()
                assert result is not None, "trading_calendar table should exist"
                assert result[0] == 1, "trading_calendar table should exist"

        finally:
            # Clean up
            if test_db_path.exists():
                test_db_path.unlink()

    def test_etf_info_table_structure(self) -> None:
        """Test that etf_info table has correct structure."""
        test_db_path = Path("test_duckdb_structure.db")

        if test_db_path.exists():
            test_db_path.unlink()

        try:
            DuckDBAdapter(str(test_db_path))

            with duckdb.connect(str(test_db_path)) as conn:
                # Get column information
                columns = conn.execute("""
                    SELECT column_name, data_type, is_nullable
                    FROM information_schema.columns
                    WHERE table_name = 'etf_info'
                    ORDER BY ordinal_position
                """).fetchall()

                # Expected columns
                expected_columns = [
                    ("symbol", "VARCHAR", "NO"),
                    ("name", "VARCHAR", "NO"),
                    ("fund_manager", "VARCHAR", "YES"),
                    ("tracking_index", "VARCHAR", "YES"),
                    ("establishment_date", "DATE", "YES"),
                    ("created_at", "TIMESTAMP", "NO"),
                    ("updated_at", "TIMESTAMP", "NO"),
                ]

                assert len(columns) == len(expected_columns)
                for i, (col_name, data_type, is_nullable) in enumerate(columns):
                    expected = expected_columns[i]
                    assert col_name == expected[0]
                    assert data_type == expected[1]
                    assert is_nullable == expected[2]

        finally:
            if test_db_path.exists():
                test_db_path.unlink()
