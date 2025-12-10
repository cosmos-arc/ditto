"""Unit tests for SQLite adapter."""

import sqlite3
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

import pytest
from ditto_core.data.adapters.sqlite_adapter import SQLiteAdapter


class TestSQLiteAdapter:
    """Test cases for SQLiteAdapter."""

    def test_init_creates_database_file(self) -> None:
        """Test that initialization creates database file and schema."""
        with TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "test.sqlite"

            # Database should not exist initially
            assert not db_path.exists()

            # Initialize adapter
            adapter = SQLiteAdapter(str(db_path))

            # Database file should be created
            assert db_path.exists()
            assert adapter.db_path == db_path
            assert adapter._connection is None

            # Clean up
            adapter.close()

    @patch("ditto_core.data.adapters.sqlite_adapter.sqlite3.connect")
    @patch("ditto_core.data.adapters.sqlite_adapter.logger")
    def test_initialize_database_logs_messages(
        self, mock_logger: MagicMock, mock_connect: MagicMock
    ) -> None:
        """Test that database initialization logs appropriate messages."""
        with TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "test.sqlite"
            mock_conn = MagicMock()
            mock_connect.return_value = mock_conn

            # Initialize adapter
            SQLiteAdapter(str(db_path))

            # Check log messages
            mock_logger.info.assert_any_call(
                f"Initializing SQLite database at {db_path}"
            )
            mock_logger.info.assert_any_call("SQLite schema created successfully")
            mock_logger.info.assert_any_call(f"SQLite adapter initialized at {db_path}")

            # Verify connection was closed
            mock_conn.close.assert_called_once()

    @patch("ditto_core.data.adapters.sqlite_adapter.sqlite3.connect")
    def test_create_schema_creates_all_tables(self, mock_connect: MagicMock) -> None:
        """Test that schema creation creates all required tables."""
        with TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "test.sqlite"
            mock_conn = MagicMock()
            mock_connect.return_value = mock_conn

            # Initialize adapter to trigger schema creation
            adapter = SQLiteAdapter(str(db_path))

            # Verify all CREATE TABLE statements were executed
            assert mock_conn.execute.call_count >= 12  # 5 tables + 7+ indexes

            # Check specific table creations
            execute_calls = [call[0][0] for call in mock_conn.execute.call_args_list]

            # Verify main tables are created
            assert any(
                "CREATE TABLE IF NOT EXISTS trades" in call for call in execute_calls
            )
            assert any(
                "CREATE TABLE IF NOT EXISTS orders" in call for call in execute_calls
            )
            assert any(
                "CREATE TABLE IF NOT EXISTS positions" in call for call in execute_calls
            )
            assert any(
                "CREATE TABLE IF NOT EXISTS portfolio_snapshots" in call
                for call in execute_calls
            )
            assert any(
                "CREATE TABLE IF NOT EXISTS strategy_configs" in call
                for call in execute_calls
            )
            assert any(
                "CREATE TABLE IF NOT EXISTS execution_logs" in call
                for call in execute_calls
            )

            # Verify indexes are created
            assert any(
                ("CREATE INDEX IF NOT EXISTS idx_trades_strategy_date" in call)
                for call in execute_calls
            )
            assert any(
                ("CREATE INDEX IF NOT EXISTS idx_trades_symbol" in call)
                for call in execute_calls
            )
            assert any(
                ("CREATE INDEX IF NOT EXISTS idx_orders_strategy" in call)
                for call in execute_calls
            )
            assert any(
                ("CREATE INDEX IF NOT EXISTS idx_orders_status" in call)
                for call in execute_calls
            )
            assert any(
                ("CREATE INDEX IF NOT EXISTS idx_positions_strategy" in call)
                for call in execute_calls
            )
            assert any(
                ("CREATE INDEX IF NOT EXISTS idx_snapshots_strategy_date" in call)
                for call in execute_calls
            )

            adapter.close()

    def test_connection_property_creates_connection(self) -> None:
        """Test that connection property creates connection when needed."""
        with TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "test.sqlite"
            adapter = SQLiteAdapter(str(db_path))

            # Connection should be None initially
            assert adapter._connection is None

            # Accessing property should create connection
            conn = adapter.connection
            assert isinstance(conn, sqlite3.Connection)
            assert adapter._connection is conn

            # Subsequent accesses should return same connection
            conn2 = adapter.connection
            assert conn is conn2

            adapter.close()

    def test_execute_with_params(self) -> None:
        """Test execute method with parameters."""
        with TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "test.sqlite"
            adapter = SQLiteAdapter(str(db_path))

            try:
                # Test simple query
                result = adapter.execute("SELECT 1 as test_col")
                assert result.fetchone() == (1,)

                # Test query with parameters
                result = adapter.execute("SELECT ? as value", (42,))
                assert result.fetchone() == (42,)

                # Test query returning multiple rows
                adapter.execute("CREATE TABLE test_table (id INTEGER, name TEXT)")
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
            db_path = Path(tmp_dir) / "test.sqlite"
            adapter = SQLiteAdapter(str(db_path))

            # Create connection by accessing property
            conn = adapter.connection
            assert adapter._connection is not None

            # Close connection
            adapter.close()
            assert adapter._connection is None

            # Verify connection is closed by trying to use it (should raise)
            with pytest.raises(sqlite3.ProgrammingError):
                conn.execute("SELECT 1")

    @patch("ditto_core.data.adapters.sqlite_adapter.logger")
    def test_close_logs_message(self, mock_logger: MagicMock) -> None:
        """Test that close method logs appropriate message."""
        with TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "test.sqlite"
            adapter = SQLiteAdapter(str(db_path))

            # Create connection first
            _ = adapter.connection

            # Close adapter
            adapter.close()

            # Verify log message
            mock_logger.info.assert_called_with("SQLite connection closed")

    def test_close_when_no_connection(self) -> None:
        """Test that close method works when no connection exists."""
        with TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "test.sqlite"
            adapter = SQLiteAdapter(str(db_path))

            # Don't create connection, just close
            adapter.close()

            # Should not raise and connection should remain None
            assert adapter._connection is None

    @patch("ditto_core.data.adapters.sqlite_adapter.sqlite3.connect")
    def test_init_with_path_object(self, mock_connect: MagicMock) -> None:
        """Test initialization with Path object instead of string."""
        with TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "test.sqlite"
            mock_conn = MagicMock()
            mock_connect.return_value = mock_conn

            # Initialize with Path object
            adapter = SQLiteAdapter(db_path)

            # Should work the same as string
            assert adapter.db_path == db_path
            mock_connect.assert_called_with(str(db_path))

            adapter.close()

    @patch("ditto_core.data.adapters.sqlite_adapter.sqlite3.connect")
    def test_database_schema_structure(self, mock_connect: MagicMock) -> None:  # noqa: PLR0915
        """Test that database schema has correct structure."""
        with TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "test.sqlite"
            mock_conn = MagicMock()
            mock_connect.return_value = mock_conn

            # Initialize adapter
            adapter = SQLiteAdapter(str(db_path))

            # Get all SQL statements
            execute_calls = [call[0][0] for call in mock_conn.execute.call_args_list]

            # Verify trades table structure
            trades_sql = next(
                call
                for call in execute_calls
                if "trades" in call and "CREATE TABLE" in call
            )
            assert "trade_id INTEGER PRIMARY KEY AUTOINCREMENT" in trades_sql
            assert "strategy_id TEXT NOT NULL" in trades_sql
            assert "symbol TEXT NOT NULL" in trades_sql
            assert "side TEXT NOT NULL CHECK (side IN ('BUY', 'SELL'))" in trades_sql
            assert "quantity INTEGER NOT NULL" in trades_sql
            assert "price REAL NOT NULL" in trades_sql
            assert "trade_date TEXT NOT NULL" in trades_sql
            assert "trade_time TEXT NOT NULL" in trades_sql
            assert "order_id TEXT NOT NULL" in trades_sql
            assert "broker TEXT NOT NULL" in trades_sql
            assert "commission REAL DEFAULT 0" in trades_sql

            # Verify orders table structure
            orders_sql = next(
                call
                for call in execute_calls
                if "orders" in call and "CREATE TABLE" in call
            )
            assert "order_id TEXT PRIMARY KEY" in orders_sql
            assert "strategy_id TEXT NOT NULL" in orders_sql
            assert "symbol TEXT NOT NULL" in orders_sql
            assert "side TEXT NOT NULL CHECK (side IN ('BUY', 'SELL'))" in orders_sql
            assert (
                "order_type TEXT NOT NULL CHECK (order_type IN ('MARKET', 'LIMIT'))"
                in orders_sql
            )
            assert "quantity INTEGER NOT NULL" in orders_sql
            assert "price REAL" in orders_sql
            assert "status TEXT NOT NULL CHECK" in orders_sql
            assert "'PENDING', 'FILLED', 'CANCELLED', 'REJECTED'" in orders_sql

            # Verify positions table structure
            positions_sql = next(
                call
                for call in execute_calls
                if "positions" in call and "CREATE TABLE" in call
            )
            assert "strategy_id TEXT NOT NULL" in positions_sql
            assert "symbol TEXT NOT NULL" in positions_sql
            assert "quantity INTEGER NOT NULL" in positions_sql
            assert "avg_price REAL NOT NULL" in positions_sql
            assert "market_value REAL" in positions_sql
            assert "unrealized_pnl REAL" in positions_sql
            assert "UNIQUE(strategy_id, symbol)" in positions_sql

            # Verify portfolio_snapshots table structure
            snapshots_sql = next(
                call
                for call in execute_calls
                if "portfolio_snapshots" in call and "CREATE TABLE" in call
            )
            assert "strategy_id TEXT NOT NULL" in snapshots_sql
            assert "total_value REAL NOT NULL" in snapshots_sql
            assert "cash_balance REAL NOT NULL" in snapshots_sql
            assert "positions_value REAL NOT NULL" in snapshots_sql
            assert "daily_pnl REAL DEFAULT 0" in snapshots_sql
            assert "max_drawdown REAL DEFAULT 0" in snapshots_sql

            # Verify strategy_configs table structure
            configs_sql = next(
                call
                for call in execute_calls
                if "strategy_configs" in call and "CREATE TABLE" in call
            )
            assert "config_id TEXT PRIMARY KEY" in configs_sql
            assert "strategy_id TEXT NOT NULL" in configs_sql
            assert "config_name TEXT NOT NULL" in configs_sql
            assert "config_json TEXT NOT NULL" in configs_sql
            assert "is_active BOOLEAN DEFAULT TRUE" in configs_sql

            # Verify execution_logs table structure
            logs_sql = next(
                call
                for call in execute_calls
                if "execution_logs" in call and "CREATE TABLE" in call
            )
            assert "strategy_id TEXT NOT NULL" in logs_sql
            assert "order_id TEXT" in logs_sql
            assert "trade_id TEXT" in logs_sql
            assert "log_level TEXT NOT NULL CHECK" in logs_sql
            assert "'DEBUG', 'INFO', 'WARNING', 'ERROR'" in logs_sql
            assert "message TEXT NOT NULL" in logs_sql

            adapter.close()

    def test_multiple_adapters_same_database(self) -> None:
        """Test that multiple adapters can access the same database."""
        with TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "shared.sqlite"

            try:
                # Create first adapter and add data
                adapter1 = SQLiteAdapter(str(db_path))
                adapter1.execute("CREATE TABLE test (id INTEGER, value TEXT)")
                adapter1.execute("INSERT INTO test VALUES (1, 'from_adapter1')")
                adapter1.connection.commit()  # Ensure data is committed
                adapter1.close()

                # Create second adapter and verify data
                adapter2 = SQLiteAdapter(str(db_path))
                result = adapter2.execute("SELECT * FROM test")
                row = result.fetchone()
                assert row == (1, "from_adapter1")

                # Add data from second adapter
                adapter2.execute("INSERT INTO test VALUES (2, 'from_adapter2')")
                adapter2.connection.commit()  # Ensure data is committed

                # Verify both rows exist
                result = adapter2.execute("SELECT * FROM test ORDER BY id")
                rows = result.fetchall()
                assert rows == [(1, "from_adapter1"), (2, "from_adapter2")]

                adapter2.close()
            except Exception:
                # Ensure cleanup on error
                if "adapter1" in locals():
                    adapter1.close()
                if "adapter2" in locals():
                    adapter2.close()
                raise

    def test_execute_with_none_params(self) -> None:
        """Test execute method with None parameters."""
        with TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "test.sqlite"
            adapter = SQLiteAdapter(str(db_path))

            try:
                # Should work without error
                result = adapter.execute("SELECT 1 as test", None)
                assert result.fetchone() == (1,)
            finally:
                adapter.close()

    def test_connection_row_factory(self) -> None:
        """Test that connection has default row factory."""
        with TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "test.sqlite"
            adapter = SQLiteAdapter(str(db_path))

            try:
                # Create test table and insert data
                adapter.execute("CREATE TABLE test (id INTEGER, name TEXT)")
                adapter.execute("INSERT INTO test VALUES (1, 'test')")

                # Query and verify default tuple row format
                result = adapter.execute("SELECT * FROM test")
                row = result.fetchone()
                assert isinstance(row, tuple)
                assert row == (1, "test")
            finally:
                adapter.close()

    def test_executemany_method(self) -> None:
        """Test executemany method with multiple parameter sets."""
        with TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "test.sqlite"
            adapter = SQLiteAdapter(str(db_path))

            try:
                # Create test table
                adapter.execute("CREATE TABLE test (id INTEGER, name TEXT, value REAL)")

                # Insert multiple rows using executemany
                params_list = [
                    (1, "first", 10.5),
                    (2, "second", 20.3),
                    (3, "third", 30.7),
                ]
                adapter.executemany(
                    "INSERT INTO test (id, name, value) VALUES (?, ?, ?)", params_list
                )
                adapter.connection.commit()

                # Verify all rows were inserted
                result = adapter.execute("SELECT * FROM test ORDER BY id")
                rows = result.fetchall()
                assert rows == [
                    (1, "first", 10.5),
                    (2, "second", 20.3),
                    (3, "third", 30.7),
                ]

                # Test executemany with UPDATE
                update_params = [("updated_first", 1), ("updated_second", 2)]
                adapter.executemany(
                    "UPDATE test SET name = ? WHERE id = ?", update_params
                )
                adapter.connection.commit()

                # Verify updates
                result = adapter.execute(
                    "SELECT name FROM test WHERE id IN (1, 2) ORDER BY id"
                )
                rows = result.fetchall()
                assert rows == [("updated_first",), ("updated_second",)]

            finally:
                adapter.close()

    def test_executemany_empty_list(self) -> None:
        """Test executemany with empty parameter list."""
        with TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "test.sqlite"
            adapter = SQLiteAdapter(str(db_path))

            try:
                # Create test table
                adapter.execute("CREATE TABLE test (id INTEGER, name TEXT)")

                # Execute with empty list - should not raise
                result = adapter.executemany("INSERT INTO test VALUES (?, ?)", [])
                assert result is not None

                # Verify no rows were inserted
                result = adapter.execute("SELECT COUNT(*) FROM test")
                count = result.fetchone()[0]
                assert count == 0

            finally:
                adapter.close()
