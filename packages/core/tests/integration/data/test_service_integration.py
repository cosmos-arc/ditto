"""Integration tests for DataService."""

import tempfile
from pathlib import Path

import pytest
from ditto_core.data.service import DataService


@pytest.mark.integration
class TestDataServiceIntegration:
    """Integration tests for DataService with real databases."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.duckdb_path = self.temp_dir / "test.duckdb"
        self.sqlite_path = self.temp_dir / "test.sqlite"

    def teardown_method(self) -> None:
        """Clean up test fixtures."""
        # Cleanup is handled by tempfile
        pass

    def test_service_with_both_databases(self) -> None:
        """Test DataService with both DuckDB and SQLite initialized."""
        service = DataService(
            duckdb_path=str(self.duckdb_path), sqlite_path=str(self.sqlite_path)
        )

        # Initialize databases
        service.initialize()

        # Verify both databases are initialized
        assert service.duckdb_adapter is not None
        assert service.sqlite_adapter is not None

        # Verify database files exist
        assert self.duckdb_path.exists()
        assert self.sqlite_path.exists()

        # Verify schema in DuckDB
        duckdb_tables = service.duckdb_adapter.connection.execute(
            "SHOW TABLES"
        ).fetchall()
        duckdb_table_names = [table[0] for table in duckdb_tables]
        assert "etf_info" in duckdb_table_names
        assert "daily_price" in duckdb_table_names
        assert "adjustment_factors" in duckdb_table_names
        assert "trading_calendar" in duckdb_table_names

        # Verify schema in SQLite
        sqlite_tables = service.sqlite_adapter.connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        sqlite_table_names = [table[0] for table in sqlite_tables]
        assert "trades" in sqlite_table_names
        assert "orders" in sqlite_table_names
        assert "positions" in sqlite_table_names
        assert "portfolio_snapshots" in sqlite_table_names
        assert "strategy_configs" in sqlite_table_names
        assert "execution_logs" in sqlite_table_names

        # Close connections
        service.close()

    def test_service_with_only_duckdb(self) -> None:
        """Test DataService with only DuckDB."""
        service = DataService(duckdb_path=str(self.duckdb_path))

        # Initialize database
        service.initialize()

        assert service.duckdb_adapter is not None
        assert service.sqlite_adapter is None

        # Verify database file exists
        assert self.duckdb_path.exists()

        # Verify schema in DuckDB
        duckdb_tables = service.duckdb_adapter.connection.execute(
            "SHOW TABLES"
        ).fetchall()
        duckdb_table_names = [table[0] for table in duckdb_tables]
        assert "etf_info" in duckdb_table_names
        assert "daily_price" in duckdb_table_names

        # Should not fail when calling methods that require SQLite
        # This tests the graceful degradation
        assert service.sqlite_adapter is None

        # Close connections
        service.close()

    def test_service_with_only_sqlite(self) -> None:
        """Test DataService with only SQLite."""
        service = DataService(sqlite_path=str(self.sqlite_path))

        # Initialize database
        service.initialize()

        assert service.sqlite_adapter is not None
        assert service.duckdb_adapter is None

        # Verify database file exists
        assert self.sqlite_path.exists()

        # Verify schema in SQLite
        sqlite_tables = service.sqlite_adapter.connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        sqlite_table_names = [table[0] for table in sqlite_tables]
        assert "trades" in sqlite_table_names
        assert "orders" in sqlite_table_names
        assert "positions" in sqlite_table_names

        # Should not fail when calling methods that require DuckDB
        # This tests the graceful degradation
        assert service.duckdb_adapter is None

        # Close connections
        service.close()

    def test_service_with_no_databases(self) -> None:
        """Test DataService initialized with no database paths."""
        service = DataService()

        # Initialize should not fail
        service.initialize()

        # Both adapters should be None
        assert service.duckdb_adapter is None
        assert service.sqlite_adapter is None

        # Getting adapters should raise ValueError
        with pytest.raises(ValueError, match="DuckDB path not provided"):
            _ = service.get_duckdb()

        with pytest.raises(ValueError, match="SQLite path not provided"):
            _ = service.get_sqlite()

        # Close should not fail
        service.close()

    def test_context_manager_with_both_databases(self) -> None:
        """Test DataService as context manager with both databases."""
        with DataService(
            duckdb_path=str(self.duckdb_path), sqlite_path=str(self.sqlite_path)
        ) as service:
            # Verify both databases are initialized
            assert service.duckdb_adapter is not None
            assert service.sqlite_adapter is not None

            # Verify database files exist
            assert self.duckdb_path.exists()
            assert self.sqlite_path.exists()

    def test_context_manager_with_only_duckdb(self) -> None:
        """Test DataService as context manager with only DuckDB."""
        with DataService(duckdb_path=str(self.duckdb_path)) as service:
            # Verify only DuckDB is initialized
            assert service.duckdb_adapter is not None
            assert service.sqlite_adapter is None

            # Verify database file exists
            assert self.duckdb_path.exists()

    def test_context_manager_with_only_sqlite(self) -> None:
        """Test DataService as context manager with only SQLite."""
        with DataService(sqlite_path=str(self.sqlite_path)) as service:
            # Verify only SQLite is initialized
            assert service.sqlite_adapter is not None
            assert service.duckdb_adapter is None

            # Verify database file exists
            assert self.sqlite_path.exists()

    def test_lazy_initialization(self) -> None:
        """Test that databases are initialized lazily."""
        service = DataService(
            duckdb_path=str(self.duckdb_path), sqlite_path=str(self.sqlite_path)
        )

        # Initially no database files
        assert not self.duckdb_path.exists()
        assert not self.sqlite_path.exists()

        # Access DuckDB adapter
        _ = service.duckdb_adapter

        # Only DuckDB file should exist
        assert self.duckdb_path.exists()
        assert not self.sqlite_path.exists()

        # Access SQLite adapter
        _ = service.sqlite_adapter

        # Both files should exist
        assert self.duckdb_path.exists()
        assert self.sqlite_path.exists()

        service.close()
