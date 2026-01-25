"""
通达信数据源 - DataHub 层.

职责：数据访问（读取通达信 .day 文件）。
仅用于质量对账，不参与主数据摄入。
"""

from pathlib import Path

import polars as pl

from ditto_datahub.config import DataSourceSettings
from ditto_datahub.sources.tdx.reader import TdxReader


class TdxSource:
    """
    通达信数据源.

    仅用于质量对账，不参与主数据摄入。
    """

    def __init__(
        self,
        data_source_settings: DataSourceSettings,
    ) -> None:
        """
        初始化通达信数据源.

        Args:
            data_source_settings: 数据源配置（包含 tdx_path）

        """
        self.tdx_path = Path(data_source_settings.tdx_path)
        self.reader = TdxReader(self.tdx_path)

    def fetch_stock_daily_bars(
        self,
        ts_codes: list[str],
        trade_date: str,
    ) -> pl.DataFrame:
        """
        获取股票日线数据.

        Args:
            ts_codes: 股票代码列表
            trade_date: 交易日期（YYYYMMDD）

        Returns:
            DataFrame with columns: src_code, trade_date, open, high, low, close, vol,
            amount

        """
        return self.reader.fetch_stock_daily_bars(ts_codes, trade_date)
