"""New DataWriter implementation without adapter abstraction."""

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


class DataWriter:
    """数据写入服务 - 直接管理数据库连接，不使用adapter抽象."""

    def __init__(
        self, duckdb_path: str | None = None, sqlite_path: str | None = None
    ) -> None:
        """
        初始化数据写入器.

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
    def for_testing(cls) -> DataWriter:
        """
        创建测试用的DataWriter实例（使用内存数据库）.

        Returns:
            DataWriter实例

        """
        # 创建临时文件数据库而不是内存数据库，以便支持多个连接
        temp_dir = tempfile.mkdtemp()
        duckdb_path = f"{temp_dir}/test_market.duckdb"
        sqlite_path = f"{temp_dir}/test_trading.sqlite"

        writer = cls(duckdb_path=duckdb_path, sqlite_path=sqlite_path)
        return writer

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

        self._sqlite_conn.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                order_id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol VARCHAR,
                side VARCHAR,
                order_type VARCHAR,
                quantity INTEGER,
                price DECIMAL(10,4),
                status VARCHAR,
                create_time DATETIME,
                update_time DATETIME,
                knowledge_date DATE
            )
        """)

        self._sqlite_conn.execute("""
            CREATE TABLE IF NOT EXISTS positions (
                position_id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol VARCHAR,
                quantity INTEGER,
                avg_price DECIMAL(10,4),
                market_value DECIMAL(20,2),
                last_update DATETIME,
                knowledge_date DATE
            )
        """)

    def store_etf_info(self, etf_data: pl.DataFrame | list[dict[str, Any]]) -> None:
        """
        Store ETF basic information.

        Args:
            etf_data: 包含ETF信息的DataFrame或字典列表

        """
        try:
            # 转换为DataFrame
            df = pl.DataFrame(etf_data) if isinstance(etf_data, list) else etf_data

            # Check for required columns
            if "symbol" not in df.columns or "name" not in df.columns:
                raise ValueError("ETF数据必须包含symbol和name列")

            # Add knowledge_date if not present
            if "knowledge_date" not in df.columns:
                df = df.with_columns(
                    [pl.lit(datetime.now().date()).alias("knowledge_date")]
                )

            # Select only required columns
            required_columns = ["symbol", "name", "list_date", "knowledge_date"]
            df = df.select(required_columns)

            # 插入数据库
            self._duck_conn.execute("INSERT OR REPLACE INTO etf_info SELECT * FROM df")
            logger.info(f"存储ETF信息: {len(df)} 条记录")
        except Exception as e:
            logger.error(f"存储ETF信息失败: {e}")
            raise

    def store_daily_data(self, daily_data: pl.DataFrame | list[dict[str, Any]]) -> None:
        """
        Store daily price data.

        Args:
            daily_data: 包含日线数据的DataFrame或字典列表

        """
        try:
            # 转换为DataFrame
            df = (
                pl.DataFrame(daily_data) if isinstance(daily_data, list) else daily_data
            )

            # Check for required columns
            required_cols = {"symbol", "date", "open", "high", "low", "close", "volume"}
            if not required_cols.issubset(df.columns):
                missing = required_cols - set(df.columns)
                raise ValueError(f"Missing required columns: {missing}")

            # Map columns to database schema
            column_mapping = {
                "date": "trade_date",
                "open": "open_price",
                "high": "high_price",
                "low": "low_price",
                "close": "close_price",
            }

            # Rename columns
            df = df.rename(column_mapping)

            # Add knowledge_date if not present
            if "knowledge_date" not in df.columns:
                df = df.with_columns(
                    [pl.lit(datetime.now().date()).alias("knowledge_date")]
                )

            # Select all columns needed for database
            db_columns = [
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

            # Add missing columns with null values
            for col in db_columns:
                if col not in df.columns:
                    df = df.with_columns(pl.lit(None).alias(col))

            # Select columns in correct order
            df = df.select(db_columns)

            # 插入数据库
            self._duck_conn.execute(
                "INSERT OR REPLACE INTO daily_price SELECT * FROM df"
            )
            logger.info(f"存储日线数据: {len(df)} 条记录")
        except Exception as e:
            logger.error(f"存储日线数据失败: {e}")
            raise

    def store_adjustment_factors(
        self, adj_data: pl.DataFrame | list[dict[str, Any]]
    ) -> None:
        """
        Store adjustment factors.

        Args:
            adj_data: 包含复权因子的DataFrame或字典列表

        """
        try:
            # 转换为DataFrame
            df = pl.DataFrame(adj_data) if isinstance(adj_data, list) else adj_data

            # Handle both 'date' and 'ex_date' column names
            if "date" not in df.columns and "ex_date" not in df.columns:
                raise ValueError(
                    "Adjustment data must contain either 'date' or 'ex_date' column"
                )

            # Rename 'date' to 'ex_date' if necessary
            if "date" in df.columns and "ex_date" not in df.columns:
                df = df.rename({"date": "ex_date"})

            # Check for required columns
            required_cols = {"symbol", "ex_date", "adj_factor"}
            if not required_cols.issubset(df.columns):
                missing = required_cols - set(df.columns)
                raise ValueError(f"Missing required columns: {missing}")

            # Add knowledge_date if not present
            if "knowledge_date" not in df.columns:
                df = df.with_columns(
                    [pl.lit(datetime.now().date()).alias("knowledge_date")]
                )

            # Select all columns needed for database
            db_columns = [
                "symbol",
                "ex_date",
                "adj_factor",
                "adj_type",
                "knowledge_date",
            ]

            # Add missing columns with null values
            for col in db_columns:
                if col not in df.columns:
                    df = df.with_columns(pl.lit(None).alias(col))

            # Select columns in correct order
            df = df.select(db_columns)

            # 插入数据库
            self._duck_conn.execute(
                "INSERT OR REPLACE INTO adjustment_factors SELECT * FROM df"
            )
            logger.info(f"存储复权因子: {len(df)} 条记录")
        except Exception as e:
            logger.error(f"存储复权因子失败: {e}")
            raise

    def store_trading_calendar(
        self, calendar_data: pl.DataFrame | list[dict[str, Any]]
    ) -> None:
        """
        Store trading calendar.

        Args:
            calendar_data: 包含交易日历的DataFrame或字典列表

        """
        try:
            # 转换为DataFrame
            df = (
                pl.DataFrame(calendar_data)
                if isinstance(calendar_data, list)
                else calendar_data
            )

            # Check for required columns
            required_cols = {"date", "is_trading_day"}
            if not required_cols.issubset(df.columns):
                missing = required_cols - set(df.columns)
                raise ValueError(f"Missing required columns: {missing}")

            # Rename 'date' to 'trade_date'
            if "date" in df.columns:
                df = df.rename({"date": "trade_date"})

            # Add knowledge_date if not present
            if "knowledge_date" not in df.columns:
                df = df.with_columns(
                    [pl.lit(datetime.now().date()).alias("knowledge_date")]
                )

            # Select all columns needed for database
            db_columns = [
                "trade_date",
                "is_trading_day",
                "market",
                "knowledge_date",
            ]

            # Add missing columns with null values
            for col in db_columns:
                if col not in df.columns:
                    df = df.with_columns(pl.lit(None).alias(col))

            # Select columns in correct order
            df = df.select(db_columns)

            # 插入数据库
            self._duck_conn.execute(
                "INSERT OR IGNORE INTO trading_calendar SELECT * FROM df"
            )
            logger.info(f"存储交易日历: {len(df)} 条记录")
        except Exception as e:
            logger.error(f"存储交易日历失败: {e}")
            raise

    def store_trades(self, trades_data: pl.DataFrame | list[dict[str, Any]]) -> None:
        """
        Store trade records.

        Args:
            trades_data: 包含交易记录的DataFrame或字典列表

        """
        try:
            # 转换为DataFrame
            df = (
                pl.DataFrame(trades_data)
                if isinstance(trades_data, list)
                else trades_data
            )

            # Check for required columns
            required_cols = {"symbol", "side", "quantity", "price"}
            if not required_cols.issubset(df.columns):
                missing = required_cols - set(df.columns)
                raise ValueError(f"Missing required columns: {missing}")

            # Add knowledge_date if not present
            if "knowledge_date" not in df.columns:
                df = df.with_columns(
                    [pl.lit(datetime.now().date()).alias("knowledge_date")]
                )

            # Add timestamp if not present
            if "timestamp" not in df.columns:
                df = df.with_columns([pl.lit(datetime.now()).alias("timestamp")])

            # Select all columns needed for database
            db_columns = [
                "symbol",
                "side",
                "quantity",
                "price",
                "timestamp",
                "knowledge_date",
            ]

            # Add missing columns with null values
            for col in db_columns:
                if col not in df.columns:
                    df = df.with_columns(pl.lit(None).alias(col))

            # Select columns in correct order
            df = df.select(db_columns)

            # Convert to dict and insert
            trades_list = df.to_dicts()
            self._sqlite_conn.executemany(
                """
                INSERT INTO trades (symbol, side, quantity, price, timestamp, knowledge_date)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        t["symbol"],
                        t["side"],
                        t["quantity"],
                        t["price"],
                        t["timestamp"],
                        t["knowledge_date"],
                    )
                    for t in trades_list
                ],
            )
            logger.info(f"存储交易记录: {len(trades_list)} 条记录")
        except Exception as e:
            logger.error(f"存储交易记录失败: {e}")
            raise

    def store_orders(self, orders_data: pl.DataFrame | list[dict[str, Any]]) -> None:
        """
        Store order records.

        Args:
            orders_data: 包含订单记录的DataFrame或字典列表

        """
        try:
            # 转换为DataFrame
            df = (
                pl.DataFrame(orders_data)
                if isinstance(orders_data, list)
                else orders_data
            )

            # Check for required columns
            required_cols = {"symbol", "side", "quantity"}
            if not required_cols.issubset(df.columns):
                missing = required_cols - set(df.columns)
                raise ValueError(f"Missing required columns: {missing}")

            # Add knowledge_date if not present
            if "knowledge_date" not in df.columns:
                df = df.with_columns(
                    [pl.lit(datetime.now().date()).alias("knowledge_date")]
                )

            # Add timestamps if not present
            if "create_time" not in df.columns:
                df = df.with_columns([pl.lit(datetime.now()).alias("create_time")])
            if "update_time" not in df.columns:
                df = df.with_columns([pl.lit(datetime.now()).alias("update_time")])

            # Select all columns needed for database
            db_columns = [
                "symbol",
                "side",
                "order_type",
                "quantity",
                "price",
                "status",
                "create_time",
                "update_time",
                "knowledge_date",
            ]

            # Add missing columns with null values
            for col in db_columns:
                if col not in df.columns:
                    df = df.with_columns(pl.lit(None).alias(col))

            # Select columns in correct order
            df = df.select(db_columns)

            # Convert to dict and insert
            orders_list = df.to_dicts()
            self._sqlite_conn.executemany(
                """
                INSERT INTO orders (symbol, side, order_type, quantity, price, status, create_time, update_time, knowledge_date)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        o["symbol"],
                        o["side"],
                        o["order_type"],
                        o["quantity"],
                        o["price"],
                        o["status"],
                        o["create_time"],
                        o["update_time"],
                        o["knowledge_date"],
                    )
                    for o in orders_list
                ],
            )
            logger.info(f"存储订单记录: {len(orders_list)} 条记录")
        except Exception as e:
            logger.error(f"存储订单记录失败: {e}")
            raise

    def store_positions(
        self, positions_data: pl.DataFrame | list[dict[str, Any]]
    ) -> None:
        """
        Store position records.

        Args:
            positions_data: 包含持仓记录的DataFrame或字典列表

        """
        try:
            # 转换为DataFrame
            df = (
                pl.DataFrame(positions_data)
                if isinstance(positions_data, list)
                else positions_data
            )

            # Check for required columns
            required_cols = {"symbol", "quantity"}
            if not required_cols.issubset(df.columns):
                missing = required_cols - set(df.columns)
                raise ValueError(f"Missing required columns: {missing}")

            # Add knowledge_date if not present
            if "knowledge_date" not in df.columns:
                df = df.with_columns(
                    [pl.lit(datetime.now().date()).alias("knowledge_date")]
                )

            # Add last_update if not present
            if "last_update" not in df.columns:
                df = df.with_columns([pl.lit(datetime.now()).alias("last_update")])

            # Select all columns needed for database
            db_columns = [
                "symbol",
                "quantity",
                "avg_price",
                "market_value",
                "last_update",
                "knowledge_date",
            ]

            # Add missing columns with null values
            for col in db_columns:
                if col not in df.columns:
                    df = df.with_columns(pl.lit(None).alias(col))

            # Select columns in correct order
            df = df.select(db_columns)

            # Convert to dict and insert
            positions_list = df.to_dicts()
            self._sqlite_conn.executemany(
                """
                INSERT INTO positions (symbol, quantity, avg_price, market_value, last_update, knowledge_date)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        p["symbol"],
                        p["quantity"],
                        p["avg_price"],
                        p["market_value"],
                        p["last_update"],
                        p["knowledge_date"],
                    )
                    for p in positions_list
                ],
            )
            logger.info(f"存储持仓记录: {len(positions_list)} 条记录")
        except Exception as e:
            logger.error(f"存储持仓记录失败: {e}")
            raise
