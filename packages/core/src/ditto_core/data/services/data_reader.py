"""New DataReader implementation without adapter abstraction."""

from __future__ import annotations

import sqlite3
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

import duckdb
import polars as pl
from ditto_foundation.config import get_settings
from loguru import logger


class DataReader:
    """数据读取服务 - 直接管理数据库连接，不使用adapter抽象."""

    def __init__(
        self, duckdb_path: str | None = None, sqlite_path: str | None = None
    ) -> None:
        """
        初始化数据读取器.

        Args:
            duckdb_path: DuckDB数据库路径
            sqlite_path: SQLite数据库路径

        """
        if duckdb_path is None or sqlite_path is None:
            settings = get_settings()
            duckdb_path = duckdb_path or str(settings.database.duckdb_path)
            sqlite_path = sqlite_path or str(settings.database.sqlite_path)

        # 确保目录存在
        Path(duckdb_path).parent.mkdir(parents=True, exist_ok=True)
        Path(sqlite_path).parent.mkdir(parents=True, exist_ok=True)

        # 创建数据库连接
        self._duck_conn = duckdb.connect(duckdb_path)
        self._sqlite_conn = sqlite3.connect(sqlite_path)

        # 初始化表结构
        self._init_schemas()

    @classmethod
    def for_testing(cls) -> DataReader:
        """
        创建测试用的DataReader实例（使用内存数据库）.

        Returns:
            DataReader实例

        """
        # 创建临时文件数据库而不是内存数据库，以便支持多个连接
        temp_dir = tempfile.mkdtemp()
        duckdb_path = f"{temp_dir}/test_market.duckdb"
        sqlite_path = f"{temp_dir}/test_trading.sqlite"

        reader = cls(duckdb_path=duckdb_path, sqlite_path=sqlite_path)
        return reader

    def _init_schemas(self) -> None:
        """初始化数据库表结构."""
        # DuckDB表（市场数据）
        self._duck_conn.execute("""
            CREATE TABLE IF NOT EXISTS etf_info (
                symbol VARCHAR PRIMARY KEY,
                name VARCHAR,
                list_date DATE,
                knowledge_date DATE
            )
        """)

        self._duck_conn.execute("""
            CREATE TABLE IF NOT EXISTS daily_price (
                symbol VARCHAR,
                trade_date DATE,
                open_price DECIMAL(10,4),
                high_price DECIMAL(10,4),
                low_price DECIMAL(10,4),
                close_price DECIMAL(10,4),
                volume BIGINT,
                amount DECIMAL(20,2),
                turnover_rate DECIMAL(8,4),
                pe_ratio DECIMAL(8,4),
                pb_ratio DECIMAL(8,4),
                knowledge_date DATE,
                PRIMARY KEY (symbol, trade_date)
            )
        """)

        self._duck_conn.execute("""
            CREATE TABLE IF NOT EXISTS adjustment_factors (
                symbol VARCHAR,
                ex_date DATE,
                adj_factor DECIMAL(12,8),
                adj_type VARCHAR,
                knowledge_date DATE,
                PRIMARY KEY (symbol, ex_date)
            )
        """)

        self._duck_conn.execute("""
            CREATE TABLE IF NOT EXISTS trading_calendar (
                trade_date DATE PRIMARY KEY,
                is_trading_day BOOLEAN,
                market VARCHAR,
                knowledge_date DATE
            )
        """)

        # SQLite表（交易数据）
        self._sqlite_conn.execute("""
            CREATE TABLE IF NOT EXISTS trades (
                trade_id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol VARCHAR,
                side VARCHAR,
                quantity INTEGER,
                price DECIMAL(10,4),
                timestamp DATETIME,
                knowledge_date DATE
            )
        """)

    def get_etf_list(self) -> pl.DataFrame:
        """
        获取ETF列表.

        Returns:
            DataFrame with columns: [symbol, name, list_date, knowledge_date]

        """
        try:
            sql = """
            SELECT symbol, name, list_date, knowledge_date
            FROM etf_info
            ORDER BY symbol
            """
            return self._duck_conn.sql(sql).pl()
        except Exception as e:
            logger.error(f"获取ETF列表失败: {e}")
            raise

    def get_daily_data(
        self, symbol: str, start_date: str, end_date: str, adjusted: bool = True
    ) -> pl.DataFrame:
        """
        获取日线数据.

        Args:
            symbol: 股票代码
            start_date: 开始日期 (YYYY-MM-DD)
            end_date: 结束日期 (YYYY-MM-DD)
            adjusted: 是否返回复权后数据

        Returns:
            DataFrame with daily OHLCV data

        """
        try:
            sql = f"""
            SELECT symbol,
                   trade_date as date,
                   open_price as open,
                   high_price as high,
                   low_price as low,
                   close_price as close,
                   volume,
                   knowledge_date
            FROM daily_price
            WHERE symbol = '{symbol}' AND trade_date >= '{start_date}' AND trade_date <= '{end_date}'
            ORDER BY trade_date
            """
            return self._duck_conn.sql(sql).pl()
        except Exception as e:
            logger.error(f"获取日线数据失败 - {symbol}: {e}")
            raise

    def get_adjustment_factors(self, symbol: str) -> pl.DataFrame:
        """
        获取复权因子.

        Args:
            symbol: 股票代码

        Returns:
            DataFrame with adjustment factors

        """
        try:
            sql = f"""
            SELECT symbol, ex_date, adj_factor, adj_type, knowledge_date
            FROM adjustment_factors
            WHERE symbol = '{symbol}'
            ORDER BY ex_date
            """
            return self._duck_conn.sql(sql).pl()
        except Exception as e:
            logger.error(f"获取复权因子失败 - {symbol}: {e}")
            raise

    def get_trading_calendar(self, start_date: str, end_date: str) -> pl.DataFrame:
        """
        获取交易日历.

        Args:
            start_date: 开始日期 (YYYY-MM-DD)
            end_date: 结束日期 (YYYY-MM-DD)

        Returns:
            DataFrame with trading days

        """
        try:
            sql = f"""
            SELECT trade_date as date, is_trading_day, market, knowledge_date
            FROM trading_calendar
            WHERE trade_date >= '{start_date}' AND trade_date <= '{end_date}'
            ORDER BY trade_date
            """
            return self._duck_conn.sql(sql).pl()
        except Exception as e:
            logger.error(f"获取交易日历失败: {e}")
            raise

    def store_etf_info(self, etf_data: list[dict[str, Any]]) -> None:
        """
        Store ETF basic information.

        Args:
            etf_data: 包含ETF信息的DataFrame

        """
        try:
            # 确保knowledge_date存在
            for item in etf_data:
                if "knowledge_date" not in item:
                    item["knowledge_date"] = datetime.now().date()

            # 转换为DataFrame，只选择需要的列
            df = pl.DataFrame(etf_data)
            required_columns = ["symbol", "name", "list_date", "knowledge_date"]

            # 确保所有列都存在
            for col in required_columns:
                if col not in df.columns:
                    df = df.with_columns(pl.lit(None).alias(col))

            # 选择正确的列顺序
            df = df.select(required_columns)

            # 插入数据库
            self._duck_conn.execute("INSERT OR REPLACE INTO etf_info SELECT * FROM df")
            logger.info(f"存储ETF信息: {len(df)} 条记录")
        except Exception as e:
            logger.error(f"存储ETF信息失败: {e}")
            raise

    def store_daily_data(self, daily_data: list[dict[str, Any]]) -> None:
        """
        Store daily price data.

        Args:
            daily_data: 包含日线数据的列表

        """
        try:
            # 确保knowledge_date存在
            for item in daily_data:
                if "knowledge_date" not in item:
                    item["knowledge_date"] = datetime.now().date()
                # 重命名date为trade_date
                if "date" in item and "trade_date" not in item:
                    item["trade_date"] = item.pop("date")
                # 重命名price字段
                if "open" in item and "open_price" not in item:
                    item["open_price"] = item.pop("open")
                if "high" in item and "high_price" not in item:
                    item["high_price"] = item.pop("high")
                if "low" in item and "low_price" not in item:
                    item["low_price"] = item.pop("low")
                if "close" in item and "close_price" not in item:
                    item["close_price"] = item.pop("close")

            # 转换为DataFrame，只选择需要的列
            df = pl.DataFrame(daily_data)
            required_columns = [
                "symbol",
                "trade_date",
                "open_price",
                "high_price",
                "low_price",
                "close_price",
                "volume",
                "amount",
                "turnover_rate",
                "pe_ratio",
                "pb_ratio",
                "knowledge_date",
            ]

            # 确保所有列都存在
            for col in required_columns:
                if col not in df.columns:
                    df = df.with_columns(pl.lit(None).alias(col))

            # 选择正确的列顺序
            df = df.select(required_columns)

            # 插入数据库
            self._duck_conn.execute(
                "INSERT OR REPLACE INTO daily_price SELECT * FROM df"
            )
            logger.info(f"存储日线数据: {len(df)} 条记录")
        except Exception as e:
            logger.error(f"存储日线数据失败: {e}")
            raise

    def store_adjustment_factors(self, adj_data: list[dict[str, Any]]) -> None:
        """
        Store adjustment factors.

        Args:
            adj_data: 包含复权因子的列表

        """
        try:
            # 确保knowledge_date存在
            for item in adj_data:
                if "knowledge_date" not in item:
                    item["knowledge_date"] = datetime.now().date()

            # 转换为DataFrame，只选择需要的列
            df = pl.DataFrame(adj_data)
            required_columns = [
                "symbol",
                "ex_date",
                "adj_factor",
                "adj_type",
                "knowledge_date",
            ]

            # 确保所有列都存在
            for col in required_columns:
                if col not in df.columns:
                    df = df.with_columns(pl.lit(None).alias(col))

            # 选择正确的列顺序
            df = df.select(required_columns)

            # 插入数据库
            self._duck_conn.execute(
                "INSERT OR REPLACE INTO adjustment_factors SELECT * FROM df"
            )
            logger.info(f"存储复权因子: {len(df)} 条记录")
        except Exception as e:
            logger.error(f"存储复权因子失败: {e}")
            raise

    def store_trading_calendar(self, calendar_data: list[dict[str, Any]]) -> None:
        """
        Store trading calendar.

        Args:
            calendar_data: 包含交易日历的列表

        """
        try:
            # 确保knowledge_date存在
            for item in calendar_data:
                if "knowledge_date" not in item:
                    item["knowledge_date"] = datetime.now().date()
                # 将date字段重命名为trade_date
                if "date" in item and "trade_date" not in item:
                    item["trade_date"] = item.pop("date")

            # 转换为DataFrame，只选择需要的列
            df = pl.DataFrame(calendar_data)
            required_columns = [
                "trade_date",
                "is_trading_day",
                "market",
                "knowledge_date",
            ]

            # 确保所有列都存在
            for col in required_columns:
                if col not in df.columns:
                    df = df.with_columns(pl.lit(None).alias(col))

            # 选择正确的列顺序
            df = df.select(required_columns)

            # 插入数据库
            self._duck_conn.execute(
                "INSERT OR IGNORE INTO trading_calendar SELECT * FROM df"
            )
            logger.info(f"存储交易日历: {len(df)} 条记录")
        except Exception as e:
            logger.error(f"存储交易日历失败: {e}")
            raise
