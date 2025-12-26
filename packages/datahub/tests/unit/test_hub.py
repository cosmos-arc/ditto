"""Tests for DataHub Facade."""

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

    def teardown_method(self) -> None:
        """Clean up test environment."""
        try:
            if hasattr(self, "hub"):
                self.hub.close()
        except Exception:
            pass
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
