"""测试 conftest.py 中的 DatabaseManager 类."""

import sys
from pathlib import Path

import duckdb
import pytest

# 添加父目录到 sys.path 以导入 conftest
sys.path.insert(0, str(Path(__file__).parent.parent))

from conftest import DatabaseManager


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
