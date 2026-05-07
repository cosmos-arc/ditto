"""摄取协调器共享常量 + 指数工具函数 — 零 ditto_application 内部模块间依赖."""

from __future__ import annotations

from typing import Literal, Protocol

import polars as pl
from ditto_data.models import Dataset

# 支持按标的摄取的数据集
SUPPORTED_INSTRUMENT_DATASETS: set[Dataset] = {
    Dataset.STOCK_DAILY,
    Dataset.ETF_DAILY,
    Dataset.INDEX_DAILY,
    Dataset.ADJ_FACTOR,
    Dataset.FUND_ADJ,
    Dataset.STOCK_STATUS,
    Dataset.VALUATION_METRICS,
    Dataset.BALANCE_SHEET,
    Dataset.INCOME_STATEMENT,
    Dataset.CASH_FLOW,
    Dataset.DIVIDEND,
    Dataset.MARGIN_TRADING,
    Dataset.PLEDGE_RATIO,
}

# A股交易所代码前缀映射
A_SHARE_CODE_LENGTH = 6
EXCHANGE_PREFIX_MAP: dict[str, str] = {
    "60": "SH",  # 上交所主板
    "68": "SH",  # 上交所科创板
    "00": "SZ",  # 深交所主板
    "30": "SZ",  # 深交所创业板
    "8": "BJ",  # 北交所
    "4": "BJ",  # 北交所
}

# 市场基准指数（Tushare source_ticker 格式）
MARKET_INDEX_CODES: list[str] = [
    "000001.SH",  # 上证指数
    "399001.SZ",  # 深证成指
    "000300.SH",  # 沪深300
    "000852.SH",  # 中证1000
    "000016.SH",  # 上证50
    "399006.SZ",  # 创业板指
    "000688.SH",  # 科创50
    "399673.SZ",  # 创业板50
]

# 风格指数（Tushare source_ticker 格式）
STYLE_INDEX_CODES: list[str] = [
    "399373.SZ",  # 大盘价值
    "399374.SZ",  # 大盘成长
    "399375.SZ",  # 中盘价值
    "399376.SZ",  # 中盘成长
    "399377.SZ",  # 小盘价值
    "399378.SZ",  # 小盘成长
    "000992.SH",  # 全指价值
    "000993.SH",  # 全指成长
    "000991.SH",  # 全指红利
]


class SWIndustryProvider(Protocol):
    """申万行业数据提供者协议."""

    def fetch_sw_industry(self, level: int = 1) -> pl.DataFrame:
        """获取申万行业分类."""
        ...


def get_sw_index_codes(
    source: SWIndustryProvider,
    level: Literal[1, 2] = 1,
) -> list[str]:
    """从数据源动态获取申万行业指数代码列表."""
    df = source.fetch_sw_industry(level=level)
    if df.is_empty():
        return []
    return df["source_ticker"].unique().sort().to_list()


def get_default_index_codes(
    include_style: bool = True,
) -> list[str]:
    """获取默认指数代码列表（仅固定配置的指数）."""
    codes = list(MARKET_INDEX_CODES)
    if include_style:
        codes.extend(STYLE_INDEX_CODES)
    return codes


def get_all_index_codes(
    source: SWIndustryProvider,
    include_style: bool = True,
    include_sw_levels: list[Literal[1, 2]] | None = None,
) -> list[str]:
    """获取所有指数代码列表（包含动态获取的 SW 行业指数）."""
    codes = get_default_index_codes(include_style=include_style)
    if include_sw_levels:
        for level in include_sw_levels:
            sw_codes = get_sw_index_codes(source, level=level)
            codes.extend(sw_codes)
    return codes


__all__ = [
    "A_SHARE_CODE_LENGTH",
    "EXCHANGE_PREFIX_MAP",
    "MARKET_INDEX_CODES",
    "STYLE_INDEX_CODES",
    "SUPPORTED_INSTRUMENT_DATASETS",
    "SWIndustryProvider",
    "get_all_index_codes",
    "get_default_index_codes",
    "get_sw_index_codes",
]
