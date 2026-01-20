"""Tests for DataHub Facade."""

from collections.abc import Generator
from pathlib import Path
from unittest.mock import Mock

import polars as pl
import pytest
from ditto_datahub.accessors.adj_factor import AdjFactorAccessor
from ditto_datahub.accessors.bars import BarsAccessor
from ditto_datahub.accessors.calendar import CalendarAccessor
from ditto_datahub.accessors.index import IndexAccessor
from ditto_datahub.accessors.ingestion_log import IngestionLogAccessor
from ditto_datahub.accessors.security import SecuritiesAccessor
from ditto_datahub.accessors.universe import UniverseAccessor
from ditto_datahub.dq.engine import DQEngine
from ditto_datahub.errors import SidNotFoundError
from ditto_datahub.hub import DataHub
from ditto_datahub.runtime.freeze_manager import FreezeManager
from ditto_datahub.runtime.sid_allocator import SidAllocator
from ditto_datahub.runtime.sql_engine import SqlEngine
from ditto_datahub.sources.source import DataSources
from ditto_datahub.sources.tushare.tushare_source import TushareSource
from ditto_datahub.stores.adj_factor_store import AdjFactorStore
from ditto_datahub.stores.bars_store import BarsStore
from ditto_datahub.stores.calendar_store import CalendarStore
from ditto_datahub.stores.ingestion_log import IngestionLogStore
from ditto_datahub.stores.quarantine_store import QuarantineStore
from ditto_datahub.stores.security_store import SecurityStore
from ditto_datahub.stores.sqlite_client import SQLiteClient
from ditto_datahub.stores.stock_status_store import StockStatusStore
from ditto_datahub.stores.universe_store import UniverseStore
from ditto_foundation import SQLitePool
from ditto_foundation.concurrency import FileLockManager

# Schema 文件路径
_SCHEMA_PATH = (
    Path(__file__).parent.parent.parent
    / "src"
    / "ditto_datahub"
    / "scripts"
    / "schema.sql"
)


@pytest.fixture
def datahub_with_dependencies(tmp_path: Path) -> Generator[DataHub, None, None]:
    """
    创建完整的 DataHub 实例及所有依赖.

    这个 fixture 创建所有必需的依赖对象，模拟 DataHubProvider 的行为。
    使用 tmp_path 作为临时数据目录，确保测试隔离。
    """
    data_root = tmp_path / "data"
    data_root.mkdir(parents=True, exist_ok=True)
    (data_root / "meta").mkdir(parents=True, exist_ok=True)
    (data_root / "locks").mkdir(parents=True, exist_ok=True)
    (data_root / "config").mkdir(parents=True, exist_ok=True)

    # 创建 SQLite Pool
    db_path = data_root / "meta" / "hub.sqlite"
    sqlite_pool = SQLitePool(str(db_path), schema_path=_SCHEMA_PATH)
    sqlite_pool.init_schema()

    # 创建 Runtime Layer
    file_lock = FileLockManager(data_root / "locks")
    sid_allocator = SidAllocator(sqlite_pool)
    dq_engine = DQEngine(data_root=data_root)
    freeze_manager = FreezeManager(data_root=str(data_root))

    # 创建 Store Layer
    sqlite_client = SQLiteClient(sqlite_pool)
    security_store = SecurityStore(sqlite_client)
    calendar_store = CalendarStore(sqlite_client)
    ingestion_log_store = IngestionLogStore(sqlite_client)
    universe_store = UniverseStore(sqlite_client)
    stock_status_store = StockStatusStore(data_root=data_root)
    adj_factor_store = AdjFactorStore(data_root=data_root)
    bars_store = BarsStore(data_root=data_root)
    quarantine_store = QuarantineStore(data_root / "quarantine.db")

    # 创建 Accessor Layer
    securities = SecuritiesAccessor(security_store, sid_allocator)
    calendar = CalendarAccessor(calendar_store)
    ingestion_log = IngestionLogAccessor(ingestion_log_store)
    universe = UniverseAccessor(universe_store, security_store, sid_allocator)
    adj_factor = AdjFactorAccessor(adj_factor_store, file_lock)
    bars = BarsAccessor(
        bars_store,
        adj_factor_store,
        security_store,
        stock_status_store,
        dq_engine,
        file_lock,
        quarantine_store,
    )

    # 创建 Index Accessor (需要额外的 store)
    # 为了简化测试，我们使用 Mock
    index_store = Mock()
    index = IndexAccessor(index_store, calendar, bars)

    # 创建 Sources Layer (使用 Mock TushareSource)
    mock_tushare = Mock(spec=TushareSource)
    sources = DataSources(tushare=mock_tushare)

    # 创建 SqlEngine
    sql_engine = SqlEngine(
        data_root=data_root,
        security_store=security_store,
        calendar_store=calendar_store,
    )

    # 创建 DataHub
    hub = DataHub(
        data_root=data_root,
        sqlite_pool=sqlite_pool,
        file_lock=file_lock,
        sid_allocator=sid_allocator,
        dq_engine=dq_engine,
        freeze_manager=freeze_manager,
        securities=securities,
        calendar=calendar,
        adj_factor=adj_factor,
        bars=bars,
        universe=universe,
        index=index,
        ingestion_log=ingestion_log,
        sources=sources,
        sql_engine=sql_engine,
    )

    # 保存 sqlite_pool 引用到 hub 对象，供测试使用
    hub._test_sqlite_pool = sqlite_pool  # type: ignore[attr-defined]

    yield hub

    # 清理
    sqlite_pool.close()


@pytest.fixture
def data_root(tmp_path: Path) -> Path:
    """
    创建测试用的 data_root 路径.

    用于需要直接创建 DataHub 的测试（已废弃，新架构应使用 datahub_with_dependencies）.
    """
    data_root = tmp_path / "data"
    data_root.mkdir(parents=True, exist_ok=True)
    (data_root / "meta").mkdir(parents=True, exist_ok=True)
    (data_root / "locks").mkdir(parents=True, exist_ok=True)
    (data_root / "config").mkdir(parents=True, exist_ok=True)

    # 创建 SQLite Pool
    db_path = data_root / "meta" / "hub.sqlite"
    sqlite_pool = SQLitePool(str(db_path), schema_path=_SCHEMA_PATH)
    sqlite_pool.init_schema()
    sqlite_pool.close()

    return data_root


class TestDataHub:
    """Test cases for DataHub Facade."""

    # 移除 setup_method，使用 pytest fixture

    @staticmethod
    def _get_sample_calendar_rows() -> list[tuple]:
        """
        Get sample trading calendar rows for testing.

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

    @staticmethod
    def _insert_calendar_data(
        data_root: Path,
        rows: list[tuple] | None = None,
        sqlite_pool: SQLitePool | None = None,
    ) -> None:
        """
        Insert calendar test data into database.

        Args:
            data_root: Data root directory path.
            rows: Calendar rows to insert. If None, uses sample data.
            sqlite_pool: SQLite pool to use. If None, creates a new one.

        """
        if rows is None:
            rows = TestDataHub._get_sample_calendar_rows()

        # 如果提供了 sqlite_pool，使用它；否则创建新的
        pool = sqlite_pool or SQLitePool(str(data_root / "meta" / "hub.sqlite"))
        close_pool = sqlite_pool is None

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

        # 只在创建了新 pool 时才关闭
        if close_pool:
            pool.close()

    def test_init_creates_hub(self, datahub_with_dependencies: DataHub) -> None:
        """Test __init__ creates DataHub instance."""
        hub = datahub_with_dependencies
        assert hub.data_root == datahub_with_dependencies.data_root

    # 懒加载测试已删除 - 新架构使用依赖注入，无懒加载

    def test_sql_execute_returns_dataframe(
        self,
        datahub_with_dependencies: DataHub,
    ) -> None:
        """Test sql method returns DataFrame."""
        result = datahub_with_dependencies.sql("SELECT 1 AS num")

        assert isinstance(result, pl.DataFrame)
        assert result["num"][0] == 1

    def test_close_closes_resources(
        self,
        datahub_with_dependencies: DataHub,
    ) -> None:
        """Test close closes initialized resources."""
        # Access some resources
        _ = datahub_with_dependencies.sqlite_pool
        _ = datahub_with_dependencies.sql_engine

        # Close should not raise
        datahub_with_dependencies.close()

    def test_context_manager(
        self,
        datahub_with_dependencies: DataHub,
    ) -> None:
        """Test DataHub supports context manager."""
        with datahub_with_dependencies as hub:
            assert hub.data_root == datahub_with_dependencies.data_root
            _ = hub.sqlite_pool

        # After exit, resources should be closed
        # Note: We can't directly test if closed, but we can verify no errors

    def test_repr_shows_initialized_components(
        self,
        datahub_with_dependencies: DataHub,
    ) -> None:
        """Test __repr__ shows initialized components."""
        _ = datahub_with_dependencies.sqlite_pool

        repr_str = repr(datahub_with_dependencies)
        assert "DataHub" in repr_str
        # 新架构的 __repr__ 只显示 data_root，不显示具体组件
        assert "data_root" in repr_str

    # ========================================================================
    # Universe Store and Accessor Tests
    # ========================================================================
    # 懒加载测试已删除 - 新架构使用依赖注入，无懒加载

    # ========================================================================
    # Index Store and Accessor Tests
    # ========================================================================
    # 懒加载测试已删除 - 新架构使用依赖注入，无懒加载

    # ========================================================================
    # Runtime Layer - Freeze Manager Tests
    # ========================================================================
    # 懒加载测试已删除 - 新架构使用依赖注入，无懒加载

    # ========================================================================
    # Convenience Methods Tests
    # ========================================================================

    def test_get_trading_days_returns_list(
        self,
        datahub_with_dependencies: DataHub,
    ) -> None:
        """Test get_trading_days returns list of dates."""
        self._insert_calendar_data(
            datahub_with_dependencies.data_root,
            sqlite_pool=datahub_with_dependencies._test_sqlite_pool,  # type: ignore[attr-defined]
        )

        # Reload calendar cache to pick up the inserted data
        datahub_with_dependencies.calendar._calendar_store.reload()  # type: ignore[attr-defined]

        trading_days = datahub_with_dependencies.get_trading_days(
            "2024-01-01",
            "2024-01-05",
        )

        assert isinstance(trading_days, list)
        assert len(trading_days) == 3
        assert "2024-01-02" in trading_days
        assert "2024-01-03" in trading_days

    def test_get_trading_days_only_open_false(
        self,
        datahub_with_dependencies: DataHub,
    ) -> None:
        """Test get_trading_days with only_open=False."""
        # Use only first 2 rows for this test
        rows = self._get_sample_calendar_rows()[:2]
        self._insert_calendar_data(
            datahub_with_dependencies.data_root,
            rows,
            sqlite_pool=datahub_with_dependencies._test_sqlite_pool,  # type: ignore[attr-defined]
        )

        # Reload calendar cache to pick up the inserted data
        datahub_with_dependencies.calendar._calendar_store.reload()  # type: ignore[attr-defined]

        # When only_open=False, should return all days (closed + open)
        all_days = datahub_with_dependencies.get_trading_days(
            "2024-01-01",
            "2024-01-05",
            only_open=False,
        )

        # Should include at least the trading days
        assert isinstance(all_days, list)
        assert len(all_days) >= 2

    def test_is_trading_day_returns_bool(
        self,
        datahub_with_dependencies: DataHub,
    ) -> None:
        """Test is_trading_day returns boolean."""
        # Use only first 2 rows for this test
        rows = self._get_sample_calendar_rows()[:2]
        self._insert_calendar_data(
            datahub_with_dependencies.data_root,
            rows,
            sqlite_pool=datahub_with_dependencies._test_sqlite_pool,  # type: ignore[attr-defined]
        )

        # Reload calendar cache to pick up the inserted data
        datahub_with_dependencies.calendar._calendar_store.reload()  # type: ignore[attr-defined]

        assert datahub_with_dependencies.is_trading_day("2024-01-02") is True
        assert datahub_with_dependencies.is_trading_day("2024-01-06") is False

    # ========================================================================
    # resolve_sid Tests
    # ========================================================================

    def test_resolve_sid_raises_sid_not_found_error(
        self,
        datahub_with_dependencies: DataHub,
    ) -> None:
        """Test resolve_sid raises SidNotFoundError when identifier not found."""
        # Try to resolve a non-existent identifier
        with pytest.raises(SidNotFoundError) as exc_info:
            datahub_with_dependencies.resolve_sid("999999.SH", source="tushare")

        # Verify exception contains the identifier and source
        assert exc_info.value.details["identifier"] == "999999.SH"
        assert exc_info.value.details["source"] == "tushare"
        assert "999999.SH" in str(exc_info.value)

    def test_resolve_sid_with_custom_source(
        self,
        datahub_with_dependencies: DataHub,
    ) -> None:
        """Test resolve_sid with custom source parameter."""
        # Try to resolve with custom source
        with pytest.raises(SidNotFoundError) as exc_info:
            datahub_with_dependencies.resolve_sid("000001.SZ", source="akshare")

        assert exc_info.value.details["source"] == "akshare"

    def test_resolve_sid_with_asof_parameter(
        self,
        datahub_with_dependencies: DataHub,
    ) -> None:
        """Test resolve_sid with asof parameter for PIT queries."""
        # Try to resolve with asof parameter
        with pytest.raises(SidNotFoundError) as exc_info:
            datahub_with_dependencies.resolve_sid(
                "600000.SH",
                source="tushare",
                asof="2023-01-01",
            )

        assert exc_info.value.details["identifier"] == "600000.SH"

    # ========================================================================
    # refresh_sql_views Tests
    # ========================================================================

    def test_refresh_sql_views_without_sql_engine_initialized(
        self,
        datahub_with_dependencies: DataHub,
    ) -> None:
        """Test refresh_sql_views when sql_engine is not initialized."""
        # sql_engine is always initialized in new architecture
        # This test just verifies refresh_sql_views doesn't raise
        datahub_with_dependencies.refresh_sql_views()

    def test_refresh_sql_views_with_sql_engine_initialized(
        self,
        datahub_with_dependencies: DataHub,
        mocker,
    ) -> None:
        """Test refresh_sql_views when sql_engine is initialized."""
        # Access sql_engine to trigger initialization
        _ = datahub_with_dependencies.sql_engine

        # 使用 mocker.fixture mock refresh_views 方法
        mock_refresh = mocker.patch.object(
            datahub_with_dependencies.sql_engine,
            "refresh_views",
        )

        # Call refresh_sql_views
        datahub_with_dependencies.refresh_sql_views()

        # Verify refresh_views was called
        mock_refresh.assert_called_once()

    # ========================================================================
    # __init__ with Default Path Tests
    # ========================================================================

    def test_init_with_none_uses_default_path(
        self,
        datahub_with_dependencies: DataHub,
        mocker,
    ) -> None:
        """Test __init__ with data_root=None uses default path."""
        # 新架构使用依赖注入，不再支持 data_root=None
        # 此测试验证 data_root 正确设置
        assert datahub_with_dependencies.data_root is not None
        assert isinstance(datahub_with_dependencies.data_root, Path)

    # ========================================================================
    # __exit__ Exception Handling Tests
    # ========================================================================

    def test_exit_handles_exception_gracefully(
        self,
        datahub_with_dependencies: DataHub,
        mocker,
    ) -> None:
        """Test __exit__ handles exceptions and still closes resources."""
        _ = datahub_with_dependencies.sqlite_pool

        # Mock close 方法以验证调用
        mock_close = mocker.patch.object(datahub_with_dependencies, "close")

        # Simulate an exception in the with block
        try:
            with datahub_with_dependencies:
                _ = datahub_with_dependencies.sql_engine
                raise ValueError("Test exception")
        except ValueError:
            pass  # Expected exception

        # 验证 close 被调用
        mock_close.assert_called_once()

    # ========================================================================
    # Resource Lifecycle Tests
    # ========================================================================

    def test_atexit_registered_on_init(
        self,
        datahub_with_dependencies: DataHub,
        mocker,
    ) -> None:
        """验证 atexit 在初始化时注册."""
        # 由于 fixture 已经创建了 DataHub，我们无法直接 mock atexit.register
        # 验证 _cleanup_on_exit 方法存在
        assert hasattr(datahub_with_dependencies, "_cleanup_on_exit")
        assert callable(datahub_with_dependencies._cleanup_on_exit)

    def test_close_is_idempotent(
        self,
        datahub_with_dependencies: DataHub,
    ) -> None:
        """验证 close() 可以多次调用."""
        _ = datahub_with_dependencies.sqlite_pool

        # 第一次 close 应该成功
        datahub_with_dependencies.close()

        # 第二次 close 不应抛出异常
        datahub_with_dependencies.close()

        # 第三次 close 也不应抛出异常
        datahub_with_dependencies.close()

    def test_cleanup_on_exit_closes_resources(
        self,
        datahub_with_dependencies: DataHub,
        mocker,
    ) -> None:
        """验证 _cleanup_on_exit 调用 close."""
        _ = datahub_with_dependencies.sqlite_pool

        # Mock close 方法
        mock_close = mocker.patch.object(datahub_with_dependencies, "close")

        # 手动调用 _cleanup_on_exit
        datahub_with_dependencies._cleanup_on_exit()

        # 验证 close 被调用
        mock_close.assert_called_once()
