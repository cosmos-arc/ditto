"""Data writer service for storing market data."""

from datetime import datetime

import polars as pl
from loguru import logger

from ..adapters.protocol import DatabaseAdapter


class DataWriter:
    """数据写入服务 - 提供业务语义的数据存储接口."""

    def __init__(self, adapter: DatabaseAdapter) -> None:
        """
        Initialize data writer.

        Args:
            adapter: Database adapter instance

        """
        self._adapter = adapter

    def store_etf_info(self, etf_data: pl.DataFrame) -> None:
        """
        Store ETF basic information.

        Args:
            etf_data: 包含ETF信息的DataFrame

        """
        try:
            # Add knowledge_date
            if "knowledge_date" not in etf_data.columns:
                etf_data = etf_data.with_columns(
                    [pl.lit(datetime.now()).alias("knowledge_date")]
                )

            # Batch insert or update
            for row in etf_data.to_dicts():
                sql = """
                INSERT OR REPLACE INTO etf_info
                (symbol, name, list_date, knowledge_date)
                VALUES (?, ?, ?, ?)
                """
                self._adapter.execute(sql, row)

            logger.info(f"存储ETF信息: {len(etf_data)} 条记录")
        except Exception as e:
            logger.error(f"存储ETF信息失败: {e}")
            raise

    def store_daily_data(self, daily_data: pl.DataFrame) -> None:
        """
        Store daily data (raw prices).

        Args:
            daily_data: 包含日线数据的DataFrame

        """
        try:
            # Ensure data format is correct
            required_cols = {"symbol", "date", "open", "high", "low", "close", "volume"}
            if not required_cols.issubset(daily_data.columns):
                missing = required_cols - set(daily_data.columns)
                raise ValueError(f"Missing required columns: {missing}")

            # Add knowledge_date
            if "knowledge_date" not in daily_data.columns:
                daily_data = daily_data.with_columns(
                    [pl.lit(datetime.now()).alias("knowledge_date")]
                )

            # Batch storage
            self._batch_insert("daily_price_raw", daily_data)
            logger.info(f"存储日线数据: {len(daily_data)} 条记录")
        except Exception as e:
            logger.error(f"存储日线数据失败: {e}")
            raise

    def store_adjustment_factors(self, adj_data: pl.DataFrame) -> None:
        """
        Store adjustment factors.

        Args:
            adj_data: 包含复权因子的DataFrame

        """
        try:
            # Add knowledge_date
            if "knowledge_date" not in adj_data.columns:
                adj_data = adj_data.with_columns(
                    [pl.lit(datetime.now()).alias("knowledge_date")]
                )

            # Batch storage
            self._batch_insert("adjustment_factors", adj_data)
            logger.info(f"存储复权因子: {len(adj_data)} 条记录")
        except Exception as e:
            logger.error(f"存储复权因子失败: {e}")
            raise

    def store_trading_calendar(self, calendar_data: pl.DataFrame) -> None:
        """
        Store trading calendar.

        Args:
            calendar_data: 包含交易日历的DataFrame

        """
        try:
            # Add knowledge_date if missing
            if "knowledge_date" not in calendar_data.columns:
                calendar_data = calendar_data.with_columns(
                    [pl.lit(datetime.now()).alias("knowledge_date")]
                )

            self._batch_insert("trading_calendar", calendar_data)
            logger.info(f"存储交易日历: {len(calendar_data)} 条记录")
        except Exception as e:
            logger.error(f"存储交易日历失败: {e}")
            raise

    def _batch_insert(self, table_name: str, data: pl.DataFrame) -> None:
        """
        Internal method for batch data insertion.

        This method handles both INSERT and UPDATE logic for data that
        might already exist in the database.
        """
        # Use different batch insert strategies for different tables
        if table_name in ["daily_price_raw", "adjustment_factors"]:
            # These tables may need to update existing records, use INSERT OR REPLACE
            for row in data.to_dicts():
                # Build dynamic SQL statement based on DataFrame columns
                columns = list(row.keys())
                placeholders = ", ".join(["?" for _ in columns])
                column_names = ", ".join(columns)

                sql = f"""
                INSERT OR REPLACE INTO {table_name}
                ({column_names})
                VALUES ({placeholders})
                """
                self._adapter.execute(sql, list(row.values()))
        # Other tables use direct batch insert with INSERT OR IGNORE
        elif len(data) > 0:
            columns = list(data.columns)
            placeholders = ", ".join(["?" for _ in columns])
            column_names = ", ".join(columns)

            sql = f"""
                INSERT OR IGNORE INTO {table_name}
                ({column_names})
                VALUES ({placeholders})
                """
            self._adapter.execute_many(sql, data.to_dicts())
