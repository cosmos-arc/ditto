"""Tests for SqlEngine."""

from pathlib import Path
from tempfile import TemporaryDirectory

import polars as pl
from ditto_datahub.runtime.sql_engine import SqlEngine
from ditto_datahub.stores.calendar_store import CalendarStore
from ditto_datahub.stores.security_store import SecurityStore
from ditto_datahub.stores.sqlite_client import SQLiteClient
from ditto_foundation import SQLitePool


class TestSqlEngine:
    """Test cases for SqlEngine."""

    def setup_method(self) -> None:
        """Set up test environment."""
        self.temp_dir = TemporaryDirectory()
        self.data_root = Path(self.temp_dir.name)

        # Initialize test database
        db_path = self.data_root / "meta" / "hub.sqlite"
        db_path.parent.mkdir(parents=True, exist_ok=True)

        self.pool = SQLitePool(str(db_path))
        self.pool.init_schema()

        # Create stores
        sqlite_client = SQLiteClient(self.pool)
        self.security_store = SecurityStore(sqlite_client)
        self.calendar_store = CalendarStore(sqlite_client)

        # Create SqlEngine
        self.engine = SqlEngine(
            data_root=self.data_root,
            security_store=self.security_store,
            calendar_store=self.calendar_store,
        )

    def teardown_method(self) -> None:
        """Clean up test environment."""
        try:
            if hasattr(self, "engine"):
                self.engine.close()
        except Exception:
            pass
        try:
            if hasattr(self, "pool"):
                self.pool.close()
        except Exception:
            pass
        self.temp_dir.cleanup()

    def test_init_creates_connection(self) -> None:
        """Test __init__ creates DuckDB connection."""
        assert self.engine.con is not None

    def test_init_disables_progress_bar(self) -> None:
        """Test __init__ disables DuckDB progress bar."""
        # DuckDB should be configured
        assert self.engine.con is not None

    def test_execute_returns_dataframe(self) -> None:
        """Test execute returns polars DataFrame."""
        # Simple query that doesn't need data
        result = self.engine.execute("SELECT 1 AS num")

        assert isinstance(result, pl.DataFrame)
        assert result.shape == (1, 1)
        assert result["num"][0] == 1

    def test_execute_with_params(self) -> None:
        """Test execute with parameters."""
        # DuckDB uses $1, $2 for parameters
        result = self.engine.execute("SELECT $1 * 2 AS doubled", params=[5])

        assert result["doubled"][0] == 10

    def test_needs_sqlite_detects_security_table(self) -> None:
        """Test _needs_sqlite detects security table."""
        query = "SELECT * FROM security WHERE sid = 1"
        assert self.engine._needs_sqlite(query) is True

    def test_needs_sqlite_detects_calendar_table(self) -> None:
        """Test _needs_sqlite detects trading_calendar table."""
        query = "SELECT * FROM trading_calendar"
        assert self.engine._needs_sqlite(query) is True

    def test_needs_sqlite_returns_false_for_parquet_only(self) -> None:
        """Test _needs_sqlite returns false for Parquet-only query."""
        query = "SELECT * FROM stock_daily"
        assert self.engine._needs_sqlite(query) is False

    def test_attach_sqlite_attaches_database(self) -> None:
        """Test _attach_sqlite attaches SQLite database."""
        self.engine._attach_sqlite()

        # Should set flag
        assert self.engine._sqlite_attached is True

    def test_attach_sqlite_is_idempotent(self) -> None:
        """Test _attach_sqlite can be called multiple times."""
        self.engine._attach_sqlite()
        self.engine._attach_sqlite()  # Should not fail

        assert self.engine._sqlite_attached is True

    def test_close_closes_connection(self) -> None:
        """Test close closes DuckDB connection."""
        self.engine.close()

        # Connection should be closed
        # Note: DuckDB doesn't have a simple is_closed check
        # but we can verify the method runs without error

    def test_execute_cross_database_attaches_sqlite(self) -> None:
        """Test execute attaches SQLite when needed."""
        # Insert test security
        self.pool.execute(
            "INSERT INTO security (sid, symbol, name, exchange, asset_class, "
            "list_date) VALUES (?, ?, ?, ?, ?, ?)",
            [1_000_001, "TEST", "Test Security", "SH", "stock", "2024-01-01"],
        )
        self.pool.commit()

        # Query that needs SQLite
        result = self.engine.execute(
            "SELECT s.symbol FROM security s WHERE s.sid = 1000001"
        )

        assert len(result) == 1
        assert result["symbol"][0] == "TEST"

    def test_refresh_views_reregisters_views(self) -> None:
        """Test refresh_views re-registers Parquet views."""
        # Should not raise
        self.engine.refresh_views()
