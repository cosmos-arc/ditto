"""Data reader service - Provides business-semantic data access interfaces."""

from typing import Any

import polars as pl
from loguru import logger


class DataReader:
    """数据读取服务 - 提供业务语义的数据访问接口."""

    def __init__(self, adapter: Any) -> None:
        """
        初始化数据读取器.

        Args:
            adapter: 数据库适配器实例

        """
        self._adapter = adapter

    def get_etf_list(self) -> pl.DataFrame:
        """
        获取ETF列表.

        Returns:
            DataFrame with columns: [symbol, name, list_date, knowledge_date, ...]

        """
        try:
            sql = """
            SELECT symbol, name, list_date, knowledge_date
            FROM etf_info
            ORDER BY symbol
            """
            return self._adapter.fetch_df(sql)
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
            if adjusted:
                # 使用复权后数据
                sql = """
                SELECT date, open, high, low, close, volume, knowledge_date
                FROM daily_price_adjusted
                WHERE symbol = ? AND date >= ? AND date <= ?
                ORDER BY date
                """
            else:
                # 使用原始数据
                sql = """
                SELECT date, open, high, low, close, volume, knowledge_date
                FROM daily_price_raw
                WHERE symbol = ? AND date >= ? AND date <= ?
                ORDER BY date
                """

            return self._adapter.fetch_df(
                sql, {"symbol": symbol, "start_date": start_date, "end_date": end_date}
            )
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
            sql = """
            SELECT symbol, ex_date, adj_factor, knowledge_date
            FROM adjustment_factors
            WHERE symbol = ?
            ORDER BY ex_date
            """
            return self._adapter.fetch_df(sql, {"symbol": symbol})
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
            sql = """
            SELECT date, is_trading_day, knowledge_date
            FROM trading_calendar
            WHERE date >= ? AND date <= ?
            ORDER BY date
            """
            return self._adapter.fetch_df(
                sql, {"start_date": start_date, "end_date": end_date}
            )
        except Exception as e:
            logger.error(f"获取交易日历失败: {e}")
            raise
