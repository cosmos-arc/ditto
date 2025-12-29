"""Tests for DataHub Facade."""

import gc
import time
from pathlib import Path
from tempfile import TemporaryDirectory

import polars as pl
from ditto_datahub.hub import DataHub
from ditto_datahub.runtime.sqlite_pool import SQLitePool


class TestDataHub:
    """Test cases for DataHub Facade."""

    def setup_method(self) -> None:
        """Set up test environment."""
        self.temp_dir = TemporaryDirectory()
        self.data_root = Path(self.temp_dir.name)

        # Create required directories
        (self.data_root / "meta").mkdir(parents=True, exist_ok=True)
        (self.data_root / "locks").mkdir(parents=True, exist_ok=True)

        # Initialize database schema
        pool = SQLitePool(str(self.data_root / "meta" / "hub.sqlite"))
        pool.init_schema()
        pool.close()

    def _get_sample_calendar_rows(self) -> list[tuple]:
        """Get sample trading calendar rows for testing.

        Returns:
            List of calendar row tuples matching trading_calendar schema.
        """
        return [
            (
                "2024-01-02",
                True,
                None,
                "2024-01-03",
                1,
                1,
                1,
                2024,
                False,
                False,
                False,
            ),
            (
                "2024-01-03",
                True,
                "2024-01-02",
                "2024-01-04",
                1,
                1,
                1,
                2024,
                False,
                False,
                False,
            ),
            (
                "2024-01-04",
                True,
                "2024-01-03",
                None,
                1,
                1,
                1,
                2024,
                False,
                False,
                False,
            ),
        ]

    def _insert_calendar_data(self, rows: list[tuple] | None = None) -> None:
        """Insert calendar test data into database.

        Args:
            rows: Calendar rows to insert. If None, uses sample data.
        """
        if rows is None:
            rows = self._get_sample_calendar_rows()

        pool = SQLitePool(str(self.data_root / "meta" / "hub.sqlite"))
        for row in rows:
            pool.execute(
                """INSERT INTO trading_calendar
                (trade_date, is_open, prev_trade_date, next_trade_date,
                 week_of_year, month, quarter, year,
                 is_week_end, is_month_end, is_quarter_end)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                row,
            )
        pool.commit()
        pool.close()

    def teardown_method(self) -> None:
        """Clean up test environment."""
        try:
            if hasattr(self, "hub"):
                self.hub.close()
        except Exception:
            pass
        # Force garbage collection to release SQLite file handles on Windows
        gc.collect()
        time.sleep(0.1)  # Small delay to let Windows release file locks
        self.temp_dir.cleanup()

    def test_init_creates_hub(self) -> None:
        """Test __init__ creates DataHub instance."""
        hub = DataHub(self.data_root)
        assert hub.data_root == self.data_root

    def test_lazy_loading_sqlite_pool(self) -> None:
        """Test sqlite_pool is lazily loaded."""
        hub = DataHub(self.data_root)
        # Before access, it shouldn't be initialized
        assert "sqlite_pool" not in hub.__dict__

        # After access, it should be initialized
        _ = hub.sqlite_pool
        assert "sqlite_pool" in hub.__dict__

    def test_lazy_loading_bars_repository(self) -> None:
        """Test bars repository is lazily loaded."""
        hub = DataHub(self.data_root)
        assert "bars" not in hub.__dict__

        _ = hub.bars
        assert "bars" in hub.__dict__

    def test_lazy_loading_sql_engine(self) -> None:
        """Test sql_engine is lazily loaded."""
        hub = DataHub(self.data_root)
        assert "sql_engine" not in hub.__dict__

        _ = hub.sql_engine
        assert "sql_engine" in hub.__dict__

    def test_sql_execute_returns_dataframe(self) -> None:
        """Test sql method returns DataFrame."""
        hub = DataHub(self.data_root)
        result = hub.sql("SELECT 1 AS num")

        assert isinstance(result, pl.DataFrame)
        assert result["num"][0] == 1

    def test_close_closes_resources(self) -> None:
        """Test close closes initialized resources."""
        hub = DataHub(self.data_root)
        # Access some resources to trigger initialization
        _ = hub.sqlite_pool
        _ = hub.sql_engine

        # Close should not raise
        hub.close()

    def test_context_manager(self) -> None:
        """Test DataHub supports context manager."""
        with DataHub(self.data_root) as hub:
            assert hub.data_root == self.data_root
            _ = hub.sqlite_pool

        # After exit, resources should be closed
        # Note: We can't directly test if closed, but we can verify no errors

    def test_repr_shows_initialized_components(self) -> None:
        """Test __repr__ shows initialized components."""
        hub = DataHub(self.data_root)
        _ = hub.sqlite_pool

        repr_str = repr(hub)
        assert "DataHub" in repr_str
        assert "sqlite_pool" in repr_str

    # ========================================================================
    # Universe Store and Repository Tests
    # ========================================================================

    def test_universe_store_lazy_loading(self) -> None:
        """Test universe_store is lazily loaded."""
        hub = DataHub(self.data_root)
        assert "universe_store" not in hub.__dict__

        _ = hub.universe_store
        assert "universe_store" in hub.__dict__

    def test_universe_repository_lazy_loading(self) -> None:
        """Test universe repository is lazily loaded."""
        hub = DataHub(self.data_root)
        assert "universe" not in hub.__dict__

        _ = hub.universe
        assert "universe" in hub.__dict__
        assert hasattr(hub.universe, "create")
        assert hasattr(hub.universe, "get_constituents")
        assert hasattr(hub.universe, "get_csi300")

    # ========================================================================
    # Index Store and Repository Tests
    # ========================================================================

    def test_index_weight_store_lazy_loading(self) -> None:
        """Test index_weight_store is lazily loaded."""
        hub = DataHub(self.data_root)
        assert "index_weight_store" not in hub.__dict__

        _ = hub.index_weight_store
        assert "index_weight_store" in hub.__dict__

    def test_index_repository_lazy_loading(self) -> None:
        """Test index repository is lazily loaded."""
        hub = DataHub(self.data_root)
        assert "index" not in hub.__dict__

        _ = hub.index
        assert "index" in hub.__dict__
        assert hasattr(hub.index, "get_bars")
        assert hasattr(hub.index, "get_constituents")
        assert hasattr(hub.index, "get_csi300_bars")

    # ========================================================================
    # Runtime Layer - Freeze Manager Tests
    # ========================================================================

    def test_freeze_manager_lazy_loading(self) -> None:
        """Test freeze manager is lazily loaded."""
        hub = DataHub(self.data_root)
        assert "freeze" not in hub.__dict__

        _ = hub.freeze
        assert "freeze" in hub.__dict__
        assert hasattr(hub.freeze, "create")
        assert hasattr(hub.freeze, "verify")
        assert hasattr(hub.freeze, "list_freezes")

    # ========================================================================
    # Convenience Methods Tests
    # ========================================================================

    def test_get_trading_days_returns_list(self) -> None:
        """Test get_trading_days returns list of dates."""
        self._insert_calendar_data()

        hub = DataHub(self.data_root)
        trading_days = hub.get_trading_days("2024-01-01", "2024-01-05")

        assert isinstance(trading_days, list)
        assert len(trading_days) == 3
        assert "2024-01-02" in trading_days
        assert "2024-01-03" in trading_days

    def test_get_trading_days_only_open_false(self) -> None:
        """Test get_trading_days with only_open=False."""
        # Use only first 2 rows for this test
        rows = self._get_sample_calendar_rows()[:2]
        self._insert_calendar_data(rows)

        hub = DataHub(self.data_root)
        # When only_open=False, should return all days (closed + open)
        all_days = hub.get_trading_days("2024-01-01", "2024-01-05", only_open=False)

        # Should include at least the trading days
        assert isinstance(all_days, list)
        assert len(all_days) >= 2

    def test_is_trading_day_returns_bool(self) -> None:
        """Test is_trading_day returns boolean."""
        # Use only first 2 rows for this test
        rows = self._get_sample_calendar_rows()[:2]
        self._insert_calendar_data(rows)

        hub = DataHub(self.data_root)
        assert hub.is_trading_day("2024-01-02") is True
        assert hub.is_trading_day("2024-01-06") is False
