"""DuckDB 数据库适配器"""

from pathlib import Path
from typing import Optional
import duckdb


class DuckDBAdapter:
    """DuckDB 数据库适配器，用于分析型数据"""

    def __init__(self, database_path: str) -> None:
        """初始化适配器"""
        self.database_path = database_path
        self.connection: Optional[duckdb.DuckDBPyConnection] = None

    def connect(self) -> None:
        """建立数据库连接"""
        # 确保目录存在
        Path(self.database_path).parent.mkdir(parents=True, exist_ok=True)

        if self.connection is None:
            self.connection = duckdb.connect(self.database_path)

    def disconnect(self) -> None:
        """关闭数据库连接"""
        if self.connection:
            self.connection.close()
            self.connection = None

    def initialize_schema(self) -> None:
        """初始化数据库表结构"""
        if not self.connection:
            raise RuntimeError("Must connect before initializing schema")

        # ETF 基础信息表
        self.connection.execute("""
            CREATE TABLE IF NOT EXISTS etf_info (
                ts_code VARCHAR NOT NULL PRIMARY KEY,
                symbol VARCHAR NOT NULL,
                name VARCHAR NOT NULL,
                manager VARCHAR,
                establish_date DATE,
                list_date DATE,
                fund_type VARCHAR,
                track_index VARCHAR,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 日线价格表
        self.connection.execute("""
            CREATE TABLE IF NOT EXISTS daily_price (
                id INTEGER PRIMARY KEY,
                ts_code VARCHAR NOT NULL,
                trade_date DATE NOT NULL,
                open FLOAT NOT NULL,
                high FLOAT NOT NULL,
                low FLOAT NOT NULL,
                close FLOAT NOT NULL,
                volume BIGINT NOT NULL,
                amount FLOAT NOT NULL,
                adj_factor FLOAT DEFAULT 1.0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(ts_code, trade_date)
            )
        """)

        # 复权因子表
        self.connection.execute("""
            CREATE TABLE IF NOT EXISTS adjustment_factors (
                id INTEGER PRIMARY KEY,
                ts_code VARCHAR NOT NULL,
                ex_date DATE NOT NULL,
                adj_factor FLOAT NOT NULL,
                dividend FLOAT DEFAULT 0,
                split_ratio FLOAT DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(ts_code, ex_date)
            )
        """)

        # 交易日历表
        self.connection.execute("""
            CREATE TABLE IF NOT EXISTS trading_calendar (
                cal_date DATE NOT NULL PRIMARY KEY,
                is_open INTEGER NOT NULL,  -- 1: 开市, 0: 休市
                pretrade INTEGER DEFAULT 0,  -- 1: 盘前
                overnight INTEGER DEFAULT 0,  -- 1: 夜盘
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 因子数据表
        self.connection.execute("""
            CREATE TABLE IF NOT EXISTS factor_data (
                id INTEGER PRIMARY KEY,
                ts_code VARCHAR NOT NULL,
                trade_date DATE NOT NULL,
                factor_name VARCHAR NOT NULL,
                factor_value FLOAT NOT NULL,
                knowledge_date DATE NOT NULL,  -- 因子可知的日期
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(ts_code, trade_date, factor_name)
            )
        """)

        # 创建索引
        self._create_indexes()

    def _create_indexes(self) -> None:
        """创建性能优化索引"""
        indexes = [
            "CREATE INDEX IF NOT EXISTS idx_daily_price_ts_code ON daily_price(ts_code)",
            "CREATE INDEX IF NOT EXISTS idx_daily_price_trade_date ON daily_price(trade_date)",
            "CREATE INDEX IF NOT EXISTS idx_adjustment_factors_ts_code ON adjustment_factors(ts_code)",
            "CREATE INDEX IF NOT EXISTS idx_factor_data_ts_code ON factor_data(ts_code)",
            "CREATE INDEX IF NOT EXISTS idx_factor_data_trade_date ON factor_data(trade_date)",
            "CREATE INDEX IF NOT EXISTS idx_factor_data_factor_name ON factor_data(factor_name)",
        ]

        for sql in indexes:
            self.connection.execute(sql)