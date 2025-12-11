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
            # Check for required columns
            if "symbol" not in etf_data.columns or "name" not in etf_data.columns:
                raise ValueError("ETF数据必须包含symbol和name列")

            # Add knowledge_date if not present
            if "knowledge_date" not in etf_data.columns:
                etf_data = etf_data.with_columns(
                    [pl.lit(datetime.now()).alias("knowledge_date")]
                )

            # Prepare the insert with fixed columns based on test expectations
            sql = """
            INSERT OR REPLACE INTO etf_info
            (symbol, name, list_date, knowledge_date)
            VALUES (?, ?, ?, ?)
            """

            for row in etf_data.to_dicts():
                self._adapter.execute(
                    sql,
                    [
                        row.get("symbol"),
                        row.get("name"),
                        row.get("list_date"),
                        row.get("knowledge_date"),
                    ],
                )

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
            # Map columns to match schema
            column_mapping = {
                "symbol": "symbol",
                "date": "trade_date",
                "open": "open_price",
                "high": "high_price",
                "low": "low_price",
                "close": "close_price",
                "volume": "volume",
                "amount": "amount",
                "turnover_rate": "turnover_rate",
                "pe_ratio": "pe_ratio",
                "pb_ratio": "pb_ratio",
            }

            # Check for required columns
            required_cols = {"symbol", "date", "open", "high", "low", "close", "volume"}
            if not required_cols.issubset(daily_data.columns):
                missing = required_cols - set(daily_data.columns)
                raise ValueError(f"Missing required columns: {missing}")

            # Select and rename columns that exist in the data
            available_columns = []
            final_columns = []
            for new_col, old_col in column_mapping.items():
                if old_col in daily_data.columns:
                    available_columns.append(old_col)
                    final_columns.append(new_col)

            # Prepare data for insert
            insert_data = daily_data.select(available_columns)
            insert_data.columns = final_columns

            # Add knowledge_date
            if "knowledge_date" not in insert_data.columns:
                insert_data = insert_data.with_columns(
                    [pl.lit(datetime.now().date()).alias("knowledge_date")]
                )

            # Use executemany for batch insert
            columns_str = ", ".join(insert_data.columns)
            placeholders = ", ".join(["?" for _ in insert_data.columns])
            sql = f"""
            INSERT OR REPLACE INTO daily_price
            ({columns_str})
            VALUES ({placeholders})
            """

            self._adapter.execute_many(sql, insert_data.to_dicts())
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
            # Handle both 'date' and 'ex_date' column names
            if "date" not in adj_data.columns and "ex_date" not in adj_data.columns:
                raise ValueError(
                    "Adjustment data must contain either 'date' or 'ex_date' column"
                )

            # Rename 'date' to 'ex_date' if necessary
            if "date" in adj_data.columns and "ex_date" not in adj_data.columns:
                adj_data = adj_data.rename({"date": "ex_date"})

            # Map columns to match schema
            column_mapping = {
                "symbol": "symbol",
                "ex_date": "ex_date",
                "adj_factor": "adj_factor",
                "adj_type": "adj_type",
                "description": "description",
            }

            # Check for required columns
            required_cols = {"symbol", "ex_date", "adj_factor", "adj_type"}
            if not required_cols.issubset(adj_data.columns):
                missing = required_cols - set(adj_data.columns)
                raise ValueError(f"Missing required columns: {missing}")

            # Select and rename columns that exist in the data
            available_columns = []
            final_columns = []
            for new_col, old_col in column_mapping.items():
                if old_col in adj_data.columns:
                    available_columns.append(old_col)
                    final_columns.append(new_col)

            # Prepare data for insert
            insert_data = adj_data.select(available_columns)
            insert_data.columns = final_columns

            # Add knowledge_date
            if "knowledge_date" not in insert_data.columns:
                insert_data = insert_data.with_columns(
                    [pl.lit(datetime.now().date()).alias("knowledge_date")]
                )

            # Use executemany for batch insert
            columns_str = ", ".join(insert_data.columns)
            placeholders = ", ".join(["?" for _ in insert_data.columns])
            sql = f"""
            INSERT OR REPLACE INTO adjustment_factors
            ({columns_str})
            VALUES ({placeholders})
            """

            self._adapter.execute_many(sql, insert_data.to_dicts())
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
            # Map columns to match schema
            column_mapping = {
                "date": "trade_date",
                "is_trading_day": "is_trading_day",
                "market": "market",
            }

            # Check for required columns
            required_cols = {"date", "is_trading_day"}
            if not required_cols.issubset(calendar_data.columns):
                missing = required_cols - set(calendar_data.columns)
                raise ValueError(f"Missing required columns: {missing}")

            # Select and rename columns that exist in the data
            available_columns = []
            final_columns = []
            for new_col, old_col in column_mapping.items():
                if old_col in calendar_data.columns:
                    available_columns.append(old_col)
                    final_columns.append(new_col)

            # Prepare data for insert
            insert_data = calendar_data.select(available_columns)
            insert_data.columns = final_columns

            # Use executemany for batch insert
            columns_str = ", ".join(insert_data.columns)
            placeholders = ", ".join(["?" for _ in insert_data.columns])
            sql = f"""
            INSERT OR IGNORE INTO trading_calendar
            ({columns_str})
            VALUES ({placeholders})
            """

            self._adapter.execute_many(sql, insert_data.to_dicts())
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
