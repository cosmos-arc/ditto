"""Unit tests for DuckDB adapter."""

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

import duckdb
import pytest
from ditto_core.data.adapters.duckdb_adapter import DuckDBAdapter


class TestDuckDBAdapter:
    """Test cases for DuckDBAdapter."""

    def test_init_creates_database_file(self) -> None:
        """Test that initialization creates database file and schema."""
        with TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "test.duckdb"

            # Database should not exist initially
            assert not db_path.exists()

            # Initialize adapter
            adapter = DuckDBAdapter(str(db_path))

            # Database file should be created
            assert db_path.exists()
            assert adapter.db_path == db_path
            assert adapter._connection is None

            # Clean up
            adapter.close()

    @patch("ditto_core.data.adapters.duckdb_adapter.duckdb.connect")
    @patch("ditto_core.data.adapters.duckdb_adapter.logger")
    def test_initialize_database_logs_messages(
        self, mock_logger: MagicMock, mock_connect: MagicMock
    ) -> None:
        """Test that database initialization logs appropriate messages."""
        with TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "test.duckdb"
            mock_conn = MagicMock()
            mock_connect.return_value = mock_conn

            # Initialize adapter
            DuckDBAdapter(str(db_path))

            # Check log messages
            mock_logger.info.assert_any_call(
                f"Initializing DuckDB database at {db_path}"
            )
            mock_logger.info.assert_any_call("DuckDB schema created successfully")

            # Verify connection was closed
            mock_conn.close.assert_called_once()

    @patch("ditto_core.data.adapters.duckdb_adapter.duckdb.connect")
    def test_create_schema_creates_all_tables(self, mock_connect: MagicMock) -> None:
        """Test that schema creation creates all required tables."""
        with TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "test.duckdb"
            mock_conn = MagicMock()
            mock_connect.return_value = mock_conn

            # Initialize adapter to trigger schema creation
            adapter = DuckDBAdapter(str(db_path))

            # Verify all CREATE TABLE statements were executed
            assert mock_conn.execute.call_count >= 8  # 4 tables + 4+ indexes

            # Check specific table creations
            execute_calls = [call[0][0] for call in mock_conn.execute.call_args_list]

            # Verify main tables are created
            assert any(
                "CREATE TABLE IF NOT EXISTS etf_info" in call for call in execute_calls
            )
            assert any(
                "CREATE TABLE IF NOT EXISTS daily_price" in call
                for call in execute_calls
            )
            assert any(
                "CREATE TABLE IF NOT EXISTS adjustment_factors" in call
                for call in execute_calls
            )
            assert any(
                "CREATE TABLE IF NOT EXISTS trading_calendar" in call
                for call in execute_calls
            )

            # Verify indexes are created
            assert any(
                ("CREATE INDEX IF NOT EXISTS idx_daily_price_symbol_date" in call)
                for call in execute_calls
            )
            assert any(
                ("CREATE INDEX IF NOT EXISTS idx_daily_price_date" in call)
                for call in execute_calls
            )
            assert any(
                ("CREATE INDEX IF NOT EXISTS idx_adjustment_factors_symbol" in call)
                for call in execute_calls
            )
            assert any(
                ("CREATE INDEX IF NOT EXISTS idx_adjustment_factors_date" in call)
                for call in execute_calls
            )

            adapter.close()

    def test_connection_property_creates_connection(self) -> None:
        """Test that connection property creates connection when needed."""
        with TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "test.duckdb"
            adapter = DuckDBAdapter(str(db_path))

            # Connection should be None initially
            assert adapter._connection is None

            # Accessing property should create connection
            conn = adapter.connection
            assert isinstance(conn, duckdb.DuckDBPyConnection)
            assert adapter._connection is conn

            # Subsequent accesses should return same connection
            conn2 = adapter.connection
            assert conn is conn2

            adapter.close()

    def test_execute_with_params(self) -> None:
        """Test execute method with parameters."""
        with TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "test.duckdb"
            adapter = DuckDBAdapter(str(db_path))

            try:
                # Test simple query
                result = adapter.execute("SELECT 1 as test_col")
                assert result.fetchone() == (1,)

                # Test query with parameters
                result = adapter.execute("SELECT ? as value", (42,))
                assert result.fetchone() == (42,)

                # Test query returning multiple rows
                adapter.execute("CREATE TABLE test_table (id INTEGER, name VARCHAR)")
                adapter.execute(
                    "INSERT INTO test_table VALUES (1, 'test1'), (2, 'test2')"
                )
                result = adapter.execute("SELECT * FROM test_table ORDER BY id")
                rows = result.fetchall()
                assert rows == [(1, "test1"), (2, "test2")]
            finally:
                # Ensure adapter is closed to release file lock
                adapter.close()

    def test_close_closes_connection(self) -> None:
        """Test that close method properly closes connection."""
        with TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "test.duckdb"
            adapter = DuckDBAdapter(str(db_path))

            try:
                # Create connection by accessing property
                conn = adapter.connection
                assert adapter._connection is not None

                # Close connection
                adapter.close()
                assert adapter._connection is None

                # Verify connection is closed by trying to use it (should raise)
                with pytest.raises(
                    (duckdb.InvalidInputException, duckdb.ConnectionException)
                ):
                    conn.execute("SELECT 1")
            finally:
                # Ensure adapter is closed
                if adapter._connection is not None:
                    adapter.close()

    @patch("ditto_core.data.adapters.duckdb_adapter.logger")
    def test_close_logs_message(self, mock_logger: MagicMock) -> None:
        """Test that close method logs appropriate message."""
        with TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "test.duckdb"
            adapter = DuckDBAdapter(str(db_path))

            # Create connection first
            _ = adapter.connection

            # Close adapter
            adapter.close()

            # Verify log message
            mock_logger.info.assert_called_with("DuckDB connection closed")

    def test_close_when_no_connection(self) -> None:
        """Test that close method works when no connection exists."""
        with TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "test.duckdb"
            adapter = DuckDBAdapter(str(db_path))

            # Don't create connection, just close
            adapter.close()

            # Should not raise and connection should remain None
            assert adapter._connection is None

    @patch("ditto_core.data.adapters.duckdb_adapter.duckdb.connect")
    def test_init_with_path_object(self, mock_connect: MagicMock) -> None:
        """Test initialization with Path object instead of string."""
        with TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "test.duckdb"
            mock_conn = MagicMock()
            mock_connect.return_value = mock_conn

            # Initialize with Path object
            adapter = DuckDBAdapter(db_path)

            # Should work the same as string
            assert adapter.db_path == db_path
            mock_connect.assert_called_with(str(db_path))

            adapter.close()

    @patch("ditto_core.data.adapters.duckdb_adapter.duckdb.connect")
    def test_database_schema_structure(self, mock_connect: MagicMock) -> None:
        """Test that database schema has correct structure."""
        with TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "test.duckdb"
            mock_conn = MagicMock()
            mock_connect.return_value = mock_conn

            # Initialize adapter
            adapter = DuckDBAdapter(str(db_path))

            # Get all SQL statements
            execute_calls = [call[0][0] for call in mock_conn.execute.call_args_list]

            # Verify etf_info table structure
            etf_info_sql = next(call for call in execute_calls if "etf_info" in call)
            assert "symbol VARCHAR PRIMARY KEY NOT NULL" in etf_info_sql
            assert "name VARCHAR NOT NULL" in etf_info_sql
            assert "fund_manager VARCHAR" in etf_info_sql
            assert "tracking_index VARCHAR" in etf_info_sql
            assert "establishment_date DATE" in etf_info_sql
            assert (
                "created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP"
                in etf_info_sql
            )
            assert (
                "updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP"
                in etf_info_sql
            )

            # Verify daily_price table structure
            daily_price_sql = next(
                call for call in execute_calls if "daily_price" in call
            )
            assert "symbol VARCHAR NOT NULL" in daily_price_sql
            assert "trade_date DATE NOT NULL" in daily_price_sql
            assert "open_price DECIMAL(10,3) NOT NULL" in daily_price_sql
            assert "high_price DECIMAL(10,3) NOT NULL" in daily_price_sql
            assert "low_price DECIMAL(10,3) NOT NULL" in daily_price_sql
            assert "close_price DECIMAL(10,3) NOT NULL" in daily_price_sql
            assert "volume BIGINT NOT NULL" in daily_price_sql
            assert "amount DECIMAL(18,2) NOT NULL" in daily_price_sql
            assert "knowledge_date DATE NOT NULL" in daily_price_sql
            assert "PRIMARY KEY (symbol, trade_date)" in daily_price_sql

            # Verify adjustment_factors table structure
            adj_factors_sql = next(
                call for call in execute_calls if "adjustment_factors" in call
            )
            assert "symbol VARCHAR NOT NULL" in adj_factors_sql
            assert "ex_date DATE NOT NULL" in adj_factors_sql
            assert "adj_factor DECIMAL(12,8) NOT NULL" in adj_factors_sql
            assert "adj_type VARCHAR(20) NOT NULL" in adj_factors_sql
            assert "description VARCHAR" in adj_factors_sql
            assert "knowledge_date DATE NOT NULL" in adj_factors_sql
            assert "PRIMARY KEY (symbol, ex_date, adj_type)" in adj_factors_sql

            # Verify trading_calendar table structure
            trading_cal_sql = next(
                call for call in execute_calls if "trading_calendar" in call
            )
            assert "trade_date DATE PRIMARY KEY" in trading_cal_sql
            assert "is_trading_day BOOLEAN NOT NULL" in trading_cal_sql
            assert "market VARCHAR(10) NOT NULL DEFAULT 'SZSE'" in trading_cal_sql

            adapter.close()

    def test_multiple_adapters_same_database(self) -> None:
        """Test that multiple adapters can access the same database."""
        with TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "shared.duckdb"

            # Create first adapter and add data
            adapter1 = DuckDBAdapter(str(db_path))
            adapter1.execute("CREATE TABLE test (id INTEGER, value VARCHAR)")
            adapter1.execute("INSERT INTO test VALUES (1, 'from_adapter1')")
            adapter1.close()

            # Create second adapter and verify data
            adapter2 = DuckDBAdapter(str(db_path))
            result = adapter2.execute("SELECT * FROM test")
            row = result.fetchone()
            assert row == (1, "from_adapter1")

            # Add data from second adapter
            adapter2.execute("INSERT INTO test VALUES (2, 'from_adapter2')")

            # Verify both rows exist
            result = adapter2.execute("SELECT * FROM test ORDER BY id")
            rows = result.fetchall()
            assert rows == [(1, "from_adapter1"), (2, "from_adapter2")]

            adapter2.close()
