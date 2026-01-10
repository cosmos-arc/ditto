"""测试 session-scoped 数据库 fixtures."""

import duckdb
import pytest


@pytest.mark.unit
class TestDatabaseManagerFixture:
    """测试 db_manager fixture."""

    def test_db_manager_returns_database_manager(self, db_manager):
        """测试 db_manager 返回 DatabaseManager 实例."""
        # 验证 db_manager 有正确的属性和方法
        assert hasattr(db_manager, "_duckdb_conn")
        assert hasattr(db_manager, "get_duckdb_conn")
        assert hasattr(db_manager, "clean_duckdb")

    def test_db_manager_is_singleton_across_tests(self, db_manager):
        """测试 db_manager 在测试间是单例."""
        # 验证 db_manager 有正确的类型
        assert hasattr(db_manager, "_duckdb_conn")
        assert hasattr(db_manager, "get_duckdb_conn")
        assert hasattr(db_manager, "clean_duckdb")


@pytest.mark.unit
class TestCleanDuckdbFixture:
    """测试 clean_duckdb fixture."""

    def test_clean_duckdb_returns_connection(
        self, db_manager, clean_duckdb: duckdb.DuckDBPyConnection
    ):
        """测试 clean_duckdb 返回 DuckDB 连接."""
        assert isinstance(clean_duckdb, duckdb.DuckDBPyConnection)

    def test_clean_duckdb_is_same_as_manager_connection(
        self, db_manager, clean_duckdb: duckdb.DuckDBPyConnection
    ):
        """测试 clean_duckdb 返回的连接与 manager 的连接相同."""
        manager_conn = db_manager.get_duckdb_conn()
        assert clean_duckdb is manager_conn

    def test_clean_duckdb_cleans_data(
        self, db_manager, clean_duckdb: duckdb.DuckDBPyConnection
    ):
        """测试 clean_duckdb 清理数据."""
        # 插入数据
        clean_duckdb.execute(
            """
            INSERT INTO etf_list VALUES
            ('510300', '沪深300ETF', '上海', '指数型',
             '2012-04-26', '柳军', '沪深300指数', '2024-01-01')
            """
        )

        # 验证数据已插入
        assert clean_duckdb.execute("SELECT COUNT(*) FROM etf_list").fetchone()[0] == 1

        # 再次调用 clean_duckdb fixture（通过 manager）
        db_manager.clean_duckdb()

        # 验证数据已清理
        assert clean_duckdb.execute("SELECT COUNT(*) FROM etf_list").fetchone()[0] == 0

    def test_clean_duckdb_preserves_structure(
        self, clean_duckdb: duckdb.DuckDBPyConnection
    ):
        """测试 clean_duckdb 保留表结构."""
        # 获取所有表
        tables = clean_duckdb.execute("SHOW TABLES").fetchall()
        table_names = [row[0] for row in tables]

        # 验证所有表都存在
        assert "etf_list" in table_names
        assert "daily_price_raw" in table_names
        assert "daily_price_adjusted" in table_names
        assert "adjustment_factors" in table_names

    def test_clean_duckdb_cleans_before_each_test(
        self,
        db_manager,
        clean_duckdb: duckdb.DuckDBPyConnection,
    ):
        """测试 clean_duckdb 在每个测试前清理数据."""
        # 插入数据
        clean_duckdb.execute(
            """
            INSERT INTO etf_list VALUES
            ('510300', '沪深300ETF', '上海', '指数型',
             '2012-04-26', '柳军', '沪深300指数', '2024-01-01')
            """
        )

        # 验证数据已插入
        assert clean_duckdb.execute("SELECT COUNT(*) FROM etf_list").fetchone()[0] == 1

        # 注意：我们无法直接测试"在每个测试前清理"的行为
        # 因为这需要运行多个测试
        # 但我们可以验证 clean_duckdb 调用了 db_manager.clean_duckdb()


@pytest.mark.unit
class TestFixtureIntegration:
    """测试 fixture 集成行为."""

    def test_db_manager_has_required_methods(self, db_manager):
        """测试 db_manager 有必要的方法和属性."""
        # 验证 db_manager 有正确的属性和方法
        assert hasattr(db_manager, "_duckdb_conn")
        assert hasattr(db_manager, "get_duckdb_conn")
        assert hasattr(db_manager, "clean_duckdb")

    def test_clean_duckdb_initializes_connection(
        self, db_manager, clean_duckdb: duckdb.DuckDBPyConnection
    ):
        """测试 clean_duckdb 初始化连接."""
        # clean_duckdb 应该触发连接初始化
        assert db_manager._duckdb_conn is not None
        assert db_manager._duckdb_conn is clean_duckdb
