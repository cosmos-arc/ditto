"""
通达信数据源 - DataHub 层.

职责：数据访问（读取通达信 .day 文件）。
仅用于质量对账，不参与主数据摄入.

标识符转换：
- 接收 symbol（如 000001）
- 查询 InstrumentStore 获取 exchange
- 转换为 TDX 格式（如 000001.SZ）
- 返回数据包含 symbol 列
"""

from collections.abc import Sequence
from pathlib import Path

import polars as pl
from loguru import logger

from ditto_datahub.config import DataSourceSettings
from ditto_datahub.domains.metadata.instrument import InstrumentStore
from ditto_datahub.sources.tdx.reader import TdxReader


class TdxSource:
    """
    通达信数据源.

    仅用于质量对账，不参与主数据摄入.

    标识符体系：
    - 接收 symbol（统一格式）
    - 内部转换为 TDX 格式的 src_code
    - 返回包含 symbol 列的数据
    """

    def __init__(
        self,
        data_source_settings: DataSourceSettings,
        instrument_store: InstrumentStore,
    ) -> None:
        """
        初始化通达信数据源.

        Args:
            data_source_settings: 数据源配置（包含 tdx_path）
            instrument_store: 证券存储（用于 symbol → exchange 转换）

        """
        self.tdx_path = Path(data_source_settings.tdx_path)
        self.reader = TdxReader(self.tdx_path)
        self._instrument_store = instrument_store

    def fetch_stock_daily_bars(
        self,
        symbols: list[str],
        trade_date: str,
    ) -> pl.DataFrame:
        """
        获取股票日线数据.

        Args:
            symbols: 股票代码列表（symbol 格式，如 000001）
            trade_date: 交易日期（YYYYMMDD）

        Returns:
            DataFrame with columns: symbol, trade_date, open, high, low, close, vol,
            amount

        """
        # 1. 批量查询 exchange 信息
        symbol_to_exchange = self._get_exchange_mapping(symbols)

        # 2. 转换为 TDX 格式（symbol.exchange）
        tdx_codes: list[str] = []
        for symbol in symbols:
            exchange = symbol_to_exchange.get(symbol)
            if exchange:
                # 转换为 TDX 交易所代码
                tdx_exchange = self._convert_to_tdx_exchange(exchange)
                tdx_codes.append(f"{symbol}.{tdx_exchange}")
            else:
                # 如果找不到 exchange，跳过
                logger.warning(
                    "Cannot find exchange for symbol",
                    event="tdx_source_no_exchange",
                    symbol=symbol,
                )
                continue

        # 3. 调用 reader 获取数据
        df = self.reader.fetch_stock_daily_bars(tdx_codes, trade_date)

        # 4. 将 src_code 列转换为 symbol 列
        if not df.is_empty() and "src_code" in df.columns:
            df = df.with_columns(
                symbol=pl.col("src_code").str.split(".").list.get(0)
            ).drop("src_code")

        return df

    def _get_exchange_mapping(self, symbols: Sequence[str | None]) -> dict[str, str]:
        """
        批量获取 symbol → exchange 映射.

        Args:
            symbols: symbol 列表（可能包含 None，对应未知 sid）

        Returns:
            {symbol: exchange} 映射字典

        """
        # TODO: 实现更高效的批量查询，从 InstrumentStore 获取
        # 目前使用默认的交易所映射规则
        mapping: dict[str, str] = {}
        for symbol in symbols:
            # 跳过空值和非字符串类型（未知 sid 无 symbol 映射）
            if not isinstance(symbol, str):
                continue
            # 根据代码前缀判断交易所
            if symbol.startswith("6") or symbol.startswith("5"):
                mapping[symbol] = "SSE"  # 上海证券交易所
            elif symbol.startswith("0") or symbol.startswith("3"):
                mapping[symbol] = "SZSE"  # 深圳证券交易所
            elif symbol.startswith("8") or symbol.startswith("4"):
                mapping[symbol] = "BSE"  # 北京证券交易所

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
