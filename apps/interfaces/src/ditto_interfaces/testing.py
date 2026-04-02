"""Port 应用测试辅助模块."""

from pathlib import Path
from typing import cast

import duckdb


class DatabaseManager:
    """
    数据库连接池管理器。

    每个测试实例独立，支持并行测试。
    """

    _duckdb_conn: duckdb.DuckDBPyConnection | None

    def __init__(self, database_path: Path | None = None) -> None:
        """
        初始化数据库管理器.

        Args:
            database_path: 数据库文件路径，如果为 None 则使用内存数据库

        """
        self._database_path = database_path
        self._duckdb_conn = None

    def get_duckdb_conn(self) -> duckdb.DuckDBPyConnection:
        """
        获取 DuckDB 连接.

        如果连接不存在，则创建新的连接并初始化表结构。
        每个测试使用独立的数据库实例。

        Returns:
            DuckDB 连接对象

        """
        if self._duckdb_conn is None:
            if self._database_path:
                self._duckdb_conn = duckdb.connect(str(self._database_path))
            else:
                self._duckdb_conn = duckdb.connect(":memory:")
            self._init_duckdb_tables()
        return self._duckdb_conn

    def _init_duckdb_tables(self) -> None:
        """初始化 DuckDB 表结构。"""
        # 此方法仅在 get_duckdb_conn 中调用，此时 _duckdb_conn 已被赋值
        conn = cast(duckdb.DuckDBPyConnection, self._duckdb_conn)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS etf_list (
                symbol VARCHAR, name VARCHAR, market VARCHAR,
                category VARCHAR, establish_date DATE, fund_manager VARCHAR,
                tracking_index VARCHAR, knowledge_date DATE
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS daily_price_raw (
                symbol VARCHAR, date DATE, open_price DOUBLE, high_price DOUBLE,
                low_price DOUBLE, close_price DOUBLE, volume BIGINT,
                amount DOUBLE, knowledge_date DATE
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS daily_price_adjusted (
                symbol VARCHAR, date DATE, open DOUBLE, high DOUBLE,
                low DOUBLE, close DOUBLE, volume BIGINT, knowledge_date DATE
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS adjustment_factors (
                symbol VARCHAR, ex_date DATE, adj_factor DOUBLE, knowledge_date DATE
            )
        """)

    def clean_duckdb(self) -> None:
        """
        清理数据.

        删除所有表中的数据，但保留表结构。
        如果连接不存在，则不执行任何操作。
        """
        if self._duckdb_conn:
            self._duckdb_conn.execute("DELETE FROM etf_list")
            self._duckdb_conn.execute("DELETE FROM daily_price_raw")
            self._duckdb_conn.execute("DELETE FROM daily_price_adjusted")
            self._duckdb_conn.execute("DELETE FROM adjustment_factors")

    def close(self) -> None:
        """关闭数据库连接。"""
        if self._duckdb_conn:
            self._duckdb_conn.close()
            self._duckdb_conn = None
