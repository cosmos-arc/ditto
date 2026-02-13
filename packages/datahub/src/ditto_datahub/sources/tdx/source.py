"""
通达信数据源 - DataHub 层.

职责：数据访问（读取通达信 .day 文件）。
仅用于质量对账，不参与主数据摄入.

标识符转换：
- 接收 ticker（如 000001）
- 查询 InstrumentStore 获取 exchange
- 转换为 TDX 格式（如 000001.SZ）
- 返回数据包含 ticker 列
"""

from collections.abc import Sequence
from pathlib import Path

import polars as pl
from loguru import logger

from ditto_datahub.config import DataSourceSettings
from ditto_datahub.sources.tdx.reader import TdxReader


class TdxSource:
    """
    通达信数据源.

    仅用于质量对账，不参与主数据摄入.

    标识符体系：
    - 接收 ticker（统一格式）
    - 内部转换为 TDX 格式的 source_ticker
    - 返回包含 ticker 列的数据
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
        tickers: list[str],
        trade_date: str,
    ) -> pl.DataFrame:
        """
        获取股票日线数据.

        Args:
            tickers: 股票代码列表（ticker 格式，如 000001）
            trade_date: 交易日期（YYYYMMDD）

        Returns:
            DataFrame with columns: ticker, trade_date, open, high, low, close, vol,
            amount

        """
        # 1. 批量查询 exchange 信息
        ticker_to_exchange = self._get_exchange_mapping(tickers)

        # 2. 转换为 TDX 格式（ticker.exchange）
        tdx_codes: list[str] = []
        for ticker in tickers:
            exchange = ticker_to_exchange.get(ticker)
            if exchange:
                # 转换为 TDX 交易所代码
                tdx_exchange = self._convert_to_tdx_exchange(exchange)
                tdx_codes.append(f"{ticker}.{tdx_exchange}")
            else:
                # 如果找不到 exchange，跳过
                logger.warning(
                    "Cannot find exchange for ticker",
                    event="tdx_source_no_exchange",
                    ticker=ticker,
                )
                continue

        # 3. 调用 reader 获取数据
        df = self.reader.fetch_stock_daily_bars(tdx_codes, trade_date)

        # 4. 将 source_ticker 列转换为 ticker 列
        if not df.is_empty() and "source_ticker" in df.columns:
            df = df.with_columns(
                ticker=pl.col("source_ticker").str.split(".").list.get(0)
            ).drop("source_ticker")

        return df

    def _get_exchange_mapping(self, tickers: Sequence[str | None]) -> dict[str, str]:
        """
        批量获取 ticker → exchange 映射.

        Args:
            tickers: ticker 列表（可能包含 None，对应未知 instrument_id）

        Returns:
            {ticker: exchange} 映射字典

        """
        # TODO: 实现更高效的批量查询，从 InstrumentStore 获取
        # 目前使用默认的交易所映射规则
        mapping: dict[str, str] = {}
        for ticker in tickers:
            # 跳过空值和非字符串类型（未知 instrument_id 无 ticker 映射）
            if not isinstance(ticker, str):
                continue
            # 根据代码前缀判断交易所
            if ticker.startswith("6") or ticker.startswith("5"):
                mapping[ticker] = "SSE"  # 上海证券交易所
            elif ticker.startswith("0") or ticker.startswith("3"):
                mapping[ticker] = "SZSE"  # 深圳证券交易所
            elif ticker.startswith("8") or ticker.startswith("4"):
                mapping[ticker] = "BSE"  # 北京证券交易所

        return mapping

    def _convert_to_tdx_exchange(self, exchange: str) -> str:
        """
        转换为 TDX 交易所代码.

        Args:
            exchange: 标准交易所代码（SSE, SZSE, BSE）

        Returns:
            TDX 交易所代码（SH, SZ, BJ）

        """
        exchange_map = {
            "SSE": "SH",
            "SZSE": "SZ",
            "BSE": "BJ",
        }
        return exchange_map.get(exchange, "SZ")
