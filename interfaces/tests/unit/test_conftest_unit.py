"""测试 conftest.py 中的 DatabaseManager 类和 fixtures."""

from unittest.mock import Mock

import duckdb
import pytest
from ditto_interfaces.testing import DatabaseManager


@pytest.mark.unit
class TestDatabaseManager:
    """测试 DatabaseManager 类."""

    def test_init(self):
        """测试初始化."""
        manager = DatabaseManager()
        assert manager._duckdb_conn is None

    def test_get_duckdb_conn_creates_connection(self):
        """测试 get_duckdb_conn 首次调用创建连接."""
        manager = DatabaseManager()
        conn = manager.get_duckdb_conn()

        assert conn is not None
        assert isinstance(conn, duckdb.DuckDBPyConnection)
        assert manager._duckdb_conn is conn

    def test_get_duckdb_conn_reuses_connection(self):
        """测试 get_duckdb_conn 多次调用复用连接."""
        manager = DatabaseManager()
        conn1 = manager.get_duckdb_conn()
        conn2 = manager.get_duckdb_conn()

        assert conn1 is conn2

    def test_tables_initialized(self):
        """测试表结构初始化."""
        manager = DatabaseManager()
        conn = manager.get_duckdb_conn()

        # 验证表是否存在
        tables = conn.execute("SHOW TABLES").fetchall()
        table_names = [row[0] for row in tables]

        assert "etf_list" in table_names
        assert "daily_price_raw" in table_names
        assert "daily_price_adjusted" in table_names
        assert "adjustment_factors" in table_names

    def test_etf_list_table_structure(self):
        """测试 etf_list 表结构."""
        manager = DatabaseManager()
        conn = manager.get_duckdb_conn()

        # 验证表结构
        schema = conn.execute("DESCRIBE etf_list").fetchall()
        column_names = [row[0] for row in schema]

        assert "symbol" in column_names
        assert "name" in column_names
        assert "market" in column_names
        assert "category" in column_names
        assert "establish_date" in column_names
        assert "fund_manager" in column_names
        assert "tracking_index" in column_names
        assert "knowledge_date" in column_names

    def test_daily_price_raw_table_structure(self):
        """测试 daily_price_raw 表结构."""
        manager = DatabaseManager()
        conn = manager.get_duckdb_conn()

        # 验证表结构
        schema = conn.execute("DESCRIBE daily_price_raw").fetchall()
        column_names = [row[0] for row in schema]

        assert "symbol" in column_names
        assert "date" in column_names
        assert "open_price" in column_names
        assert "high_price" in column_names
        assert "low_price" in column_names
        assert "close_price" in column_names
        assert "volume" in column_names
        assert "amount" in column_names
        assert "knowledge_date" in column_names

    def test_daily_price_adjusted_table_structure(self):
        """测试 daily_price_adjusted 表结构."""
        manager = DatabaseManager()
        conn = manager.get_duckdb_conn()

        # 验证表结构
        schema = conn.execute("DESCRIBE daily_price_adjusted").fetchall()
        column_names = [row[0] for row in schema]

        assert "symbol" in column_names
        assert "date" in column_names
        assert "open" in column_names
        assert "high" in column_names
        assert "low" in column_names
        assert "close" in column_names
        assert "volume" in column_names
        assert "knowledge_date" in column_names

    def test_adjustment_factors_table_structure(self):
        """测试 adjustment_factors 表结构."""
        manager = DatabaseManager()
        conn = manager.get_duckdb_conn()

        # 验证表结构
        schema = conn.execute("DESCRIBE adjustment_factors").fetchall()
        column_names = [row[0] for row in schema]

        assert "symbol" in column_names
        assert "ex_date" in column_names
        assert "adj_factor" in column_names
        assert "knowledge_date" in column_names

    def test_clean_duckdb_deletes_all_data(self):
        """测试 clean_duckdb 清理所有表数据."""
        manager = DatabaseManager()
        conn = manager.get_duckdb_conn()

        # 插入测试数据
        conn.execute(
            """
            INSERT INTO etf_list VALUES
            ('510300', '沪深300ETF', '上海', '指数型',
             '2012-04-26', '柳军', '沪深300指数', '2024-01-01')
            """
        )
        conn.execute(
            """
            INSERT INTO daily_price_raw VALUES
            ('510300', '2024-01-01', 3.5, 3.6, 3.4, 3.55,
             1000000, 3550000.0, '2024-01-01')
            """
        )
        conn.execute("""
            INSERT INTO daily_price_adjusted VALUES
            ('510300', '2024-01-01', 3.5, 3.6, 3.4, 3.55, 1000000, '2024-01-01')
        """)
        conn.execute("""
            INSERT INTO adjustment_factors VALUES
            ('510300', '2024-01-01', 1.0, '2024-01-01')
        """)

        # 验证数据已插入
        assert conn.execute("SELECT COUNT(*) FROM etf_list").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM daily_price_raw").fetchone()[0] == 1
        assert (
            conn.execute("SELECT COUNT(*) FROM daily_price_adjusted").fetchone()[0] == 1
        )
        assert (
            conn.execute("SELECT COUNT(*) FROM adjustment_factors").fetchone()[0] == 1
        )

        # 清理数据
        manager.clean_duckdb()

        # 验证所有表已清空
        assert conn.execute("SELECT COUNT(*) FROM etf_list").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM daily_price_raw").fetchone()[0] == 0
        assert (
            conn.execute("SELECT COUNT(*) FROM daily_price_adjusted").fetchone()[0] == 0
        )
        assert (
            conn.execute("SELECT COUNT(*) FROM adjustment_factors").fetchone()[0] == 0
        )

    def test_clean_duckdb_preserves_table_structure(self):
        """测试 clean_duckdb 保留表结构."""
        manager = DatabaseManager()
        conn = manager.get_duckdb_conn()

        # 插入测试数据
        conn.execute(
            """
            INSERT INTO etf_list VALUES
            ('510300', '沪深300ETF', '上海', '指数型',
             '2012-04-26', '柳军', '沪深300指数', '2024-01-01')
            """
        )

        # 清理数据
        manager.clean_duckdb()

        # 验证表结构仍然存在
        tables = conn.execute("SHOW TABLES").fetchall()
        table_names = [row[0] for row in tables]

        assert "etf_list" in table_names
        assert "daily_price_raw" in table_names
        assert "daily_price_adjusted" in table_names
        assert "adjustment_factors" in table_names

    def test_clean_duckdb_with_no_data(self):
        """测试 clean_duckdb 在没有数据时也能正常工作."""
        manager = DatabaseManager()
        conn = manager.get_duckdb_conn()

        # 在没有数据的情况下清理
        manager.clean_duckdb()

        # 验证表结构仍然存在
        tables = conn.execute("SHOW TABLES").fetchall()
        assert len(tables) == 4

    def test_clean_duckdb_without_connection(self):
        """测试 clean_duckdb 在没有连接时也能正常工作."""
        manager = DatabaseManager()

        # 在没有创建连接的情况下清理
        manager.clean_duckdb()

        # 验证连接仍然为 None（因为没有创建过连接）
        assert manager._duckdb_conn is None

    def test_multiple_managers_independent(self):
        """测试多个 DatabaseManager 实例独立."""
        manager1 = DatabaseManager()
        manager2 = DatabaseManager()

        conn1 = manager1.get_duckdb_conn()
        conn2 = manager2.get_duckdb_conn()

        # 每个管理器应该有独立的连接
        assert conn1 is not conn2

        # 在第一个连接中插入数据
        conn1.execute(
            """
            INSERT INTO etf_list VALUES
            ('510300', '沪深300ETF', '上海', '指数型',
             '2012-04-26', '柳军', '沪深300指数', '2024-01-01')
            """
        )

        # 第一个连接应该有数据
        assert conn1.execute("SELECT COUNT(*) FROM etf_list").fetchone()[0] == 1

        # 第二个连接应该没有数据
        assert conn2.execute("SELECT COUNT(*) FROM etf_list").fetchone()[0] == 0


@pytest.mark.unit
class TestMockDataFixture:
    """测试 mock_data fixture."""

    def test_mock_data_exists(self, mock_data: Mock):
        """测试 mock_data fixture 存在并可正常工作."""
        # 验证 fixture 返回的是 Mock 对象
        assert mock_data is not None
        assert isinstance(mock_data, Mock)

    def test_mock_data_metadata_service_mock(self, mock_data: Mock):
        """测试 metadata_service mock 配置."""
        # 验证 metadata_service.is_trading_day 返回 True
        assert mock_data.metadata_service.is_trading_day() is True

        # 验证 metadata_service.resolve_instrument_id 返回正确 ID
        assert mock_data.metadata_service.resolve_instrument_id() == 1

    def test_mock_data_market_service_mock(self, mock_data: Mock):
        """测试 market_service mock 配置."""
        # 验证 market_service.query 返回空 DataFrame
        import polars as pl

        result = mock_data.market_service.query()
        assert isinstance(result, pl.DataFrame)
        assert result.height == 0  # 空表

    def test_mock_data_ingestion_log_mock(self, mock_data: Mock):
        """测试 ingestion_log mock 配置."""
        # 验证 ingestion_log.list_failed_dates 返回空列表
        assert mock_data.ingestion_log_store.list_failed_dates() == []

        # 验证 ingestion_log.list_ingested_dates 返回空列表
        assert mock_data.ingestion_log_store.list_ingested_dates() == []

    def test_mock_data_is_function_scoped(self, mock_data: Mock):
        """测试 fixture 是 function 级别的（通过验证可以多次调用）."""
        # 多次调用同一个 mock 方法，应该返回相同的结果
        result1 = mock_data.metadata_service.is_trading_day()
        result2 = mock_data.metadata_service.is_trading_day()
        assert result1 is result2 is True


@pytest.mark.unit
class TestPatchDataFixture:
    """测试 patch_data fixture."""

    def test_patch_data_fixture_exists(self, patch_data: Mock) -> None:
        """验证 patch_data fixture 存在并返回 Mock."""
        # 验证返回的是 Mock
        assert patch_data is not None
        assert isinstance(patch_data, Mock)

    def test_patch_data_has_default_mock_behavior(
        self, patch_data: Mock, mock_data: Mock
    ) -> None:
        """验证 patch_data 具有默认的 mock 行为."""
        # patch_data 返回的是 mock_data
        # 所以行为应该一致
        assert patch_data.metadata_service.is_trading_day() is True

        # 验证 metadata_service 的默认返回值
        assert patch_data.metadata_service.resolve_instrument_id() == 1

        # 验证 ingestion_log 的默认返回值
        assert patch_data.ingestion_log_store.list_failed_dates() == []
        assert patch_data.ingestion_log_store.list_ingested_dates() == []

    def test_patch_data_can_modify_mock_behavior(self, patch_data: Mock) -> None:
        """验证可以通过 patch_data 修改 mock 行为."""
        # 修改 metadata_service.is_trading_day 的返回值
        patch_data.metadata_service.is_trading_day.return_value = False

        # 验证修改生效
        assert patch_data.metadata_service.is_trading_day() is False

    def test_patch_data_returns_mock(self, patch_data: Mock, mock_data: Mock) -> None:
        """
        验证 patch_data 返回 mock 对象（不进行全局 patch）.

        注意：此 fixture 不再全局 patch Data 类，
        因为会与 dishka 依赖注入容器冲突。
        它只返回一个 mock 对象供单元测试使用。
        """
        # patch_data 应该返回 mock_data
        assert patch_data is mock_data

        # patch_data 应该有默认的 mock 行为
        assert patch_data.metadata_service.is_trading_day() is True
        assert patch_data.ingestion_log_store.list_failed_dates() == []

        # Data 类不存在（已被删除），所以不需要测试创建 Data
        # 如果尝试导入会失败
        with pytest.raises(ImportError):
            from ditto_data import DataHub  # noqa: F401
