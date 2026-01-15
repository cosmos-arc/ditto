"""Tests for DataHub Facade."""

import atexit
import gc
import time
from pathlib import Path
from tempfile import TemporaryDirectory

import polars as pl
import pytest
from ditto_datahub.errors import SidNotFoundError
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
                # 在测试中，手动 close 并取消 atexit 注册
                # 避免 Windows 文件锁问题
                self.hub.close()
                # 尝试取消 atexit 注册（如果存在）
                try:
                    atexit.unregister(self.hub._cleanup_on_exit)
                except (ValueError, AttributeError):
                    # ValueError: 未注册
                    # AttributeError: 方法不存在（旧版本兼容）
                    pass
        except Exception:  # noqa: S110 - cleanup should not raise
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
        with DataHub(self.data_root) as hub:
            assert "sql_engine" not in hub.__dict__

            _ = hub.sql_engine
            assert "sql_engine" in hub.__dict__

    def test_sql_execute_returns_dataframe(self) -> None:
        """Test sql method returns DataFrame."""
        with DataHub(self.data_root) as hub:
            result = hub.sql("SELECT 1 AS num")

            assert isinstance(result, pl.DataFrame)
            assert result["num"][0] == 1

    def test_close_closes_resources(self) -> None:
        """Test close closes initialized resources."""
        with DataHub(self.data_root) as hub:
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

        with DataHub(self.data_root) as hub:
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

        with DataHub(self.data_root) as hub:
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

        with DataHub(self.data_root) as hub:
            assert hub.is_trading_day("2024-01-02") is True
            assert hub.is_trading_day("2024-01-06") is False

    # ========================================================================
    # resolve_sid Tests
    # ========================================================================

    def test_resolve_sid_raises_sid_not_found_error(self) -> None:
        """Test resolve_sid raises SidNotFoundError when identifier not found."""

        with DataHub(self.data_root) as hub:
            # Try to resolve a non-existent identifier
            with pytest.raises(SidNotFoundError) as exc_info:
                hub.resolve_sid("999999.SH", source="tushare")

            # Verify exception contains the identifier and source
            assert exc_info.value.details["identifier"] == "999999.SH"
            assert exc_info.value.details["source"] == "tushare"
            assert "999999.SH" in str(exc_info.value)

    def test_resolve_sid_with_custom_source(self) -> None:
        """Test resolve_sid with custom source parameter."""

        with DataHub(self.data_root) as hub:
            # Try to resolve with custom source
            with pytest.raises(SidNotFoundError) as exc_info:
                hub.resolve_sid("000001.SZ", source="akshare")

            assert exc_info.value.details["source"] == "akshare"

    def test_resolve_sid_with_asof_parameter(self) -> None:
        """Test resolve_sid with asof parameter for PIT queries."""

        with DataHub(self.data_root) as hub:
            # Try to resolve with asof parameter
            with pytest.raises(SidNotFoundError) as exc_info:
                hub.resolve_sid("600000.SH", source="tushare", asof="2023-01-01")

            assert exc_info.value.details["identifier"] == "600000.SH"

    # ========================================================================
    # refresh_sql_views Tests
    # ========================================================================

    def test_refresh_sql_views_without_sql_engine_initialized(self) -> None:
        """Test refresh_sql_views when sql_engine is not initialized."""
        with DataHub(self.data_root) as hub:
            # sql_engine not accessed yet, should not be in __dict__
            assert "sql_engine" not in hub.__dict__

            # Should not raise any error
            hub.refresh_sql_views()

            # sql_engine should still not be initialized
            assert "sql_engine" not in hub.__dict__

    def test_refresh_sql_views_with_sql_engine_initialized(self, mocker) -> None:
        """Test refresh_sql_views when sql_engine is initialized."""
        with DataHub(self.data_root) as hub:
            # Access sql_engine to trigger initialization
            _ = hub.sql_engine
            assert "sql_engine" in hub.__dict__

            # 使用 mocker.fixture mock refresh_views 方法
            mock_refresh = mocker.patch.object(hub.sql_engine, "refresh_views")

            # Call refresh_sql_views
            hub.refresh_sql_views()

            # Verify refresh_views was called
            mock_refresh.assert_called_once()

    # ========================================================================
    # __init__ with Default Path Tests
    # ========================================================================

    def test_init_with_none_uses_default_path(self, mocker) -> None:
        """Test __init__ with data_root=None uses default path."""

        # Mock get_paths 返回值
        mock_path_obj = Path("D:/test/ditto/data")

        # 使用 mocker.patch 替代 patch
        mock_get_paths = mocker.patch("ditto_foundation.config.paths.get_paths")
        mock_get_paths.return_value.data_home = mock_path_obj

        with DataHub(data_root=None) as hub:
            # Verify default path was used
            assert hub.data_root == mock_path_obj
            mock_get_paths.assert_called_once()

    # ========================================================================
    # __exit__ Exception Handling Tests
    # ========================================================================

    def test_exit_handles_exception_gracefully(self, mocker) -> None:
        """Test __exit__ handles exceptions and still closes resources."""
        hub = DataHub(self.data_root)
        self.hub = hub  # 保存引用供 teardown 使用

        _ = hub.sqlite_pool

        # Mock close 方法以验证调用
        mock_close = mocker.patch.object(hub, "close")

        # Simulate an exception in the with block
        try:
            with hub:
                _ = hub.sql_engine
                raise ValueError("Test exception")
        except ValueError:
            pass  # Expected exception

        # 验证 close 被调用
        mock_close.assert_called_once()

        # 手动清理 (teardown 会再次调用，但 close 是幂等的)
        try:
            atexit.unregister(hub._cleanup_on_exit)
        except (ValueError, AttributeError):
            pass
        hub.close()

    # ========================================================================
    # Resource Lifecycle Tests
    # ========================================================================

    def test_atexit_registered_on_init(self, mocker) -> None:
        """验证 atexit 在初始化时注册."""
        # Mock atexit.register 来跟踪调用
        mock_register = mocker.patch("atexit.register")

        DataHub(self.data_root)

        # 验证 atexit.register 被调用了一次
        mock_register.assert_called_once()
        # 验证注册的是 hub 的清理方法
        args, _ = mock_register.call_args
        assert args[0].__name__ == "_cleanup_on_exit"

    def test_close_is_idempotent(self) -> None:
        """验证 close() 可以多次调用."""
        hub = DataHub(self.data_root)
        _ = hub.sqlite_pool

        # 第一次 close 应该成功
        hub.close()

        # 第二次 close 不应抛出异常
        hub.close()

        # 第三次 close 也不应抛出异常
        hub.close()

    def test_cleanup_on_exit_closes_resources(self, mocker) -> None:
        """验证 _cleanup_on_exit 调用 close."""
        hub = DataHub(self.data_root)
        _ = hub.sqlite_pool

        # Mock close 方法
        mock_close = mocker.patch.object(hub, "close")

        # 手动调用 _cleanup_on_exit
        hub._cleanup_on_exit()

        # 验证 close 被调用
        mock_close.assert_called_once()
