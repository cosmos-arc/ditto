"""
摄取协调器共享常量 + 指数工具函数.

指数静态清单（MARKET/STYLE_INDEX_CODES）的权威定义在
dataset_registry（fetch 路由层），本模块不 re-export.
"""

from __future__ import annotations

from typing import Literal, Protocol

import polars as pl
from ditto_data.models import Dataset

from ditto_application.processes.ingestion.dataset_registry import (
    MARKET_INDEX_CODES,
    STYLE_INDEX_CODES,
    default_dataset_registry,
)

# 支持按标的摄取的数据集，由 DatasetRegistry 中的 instrument_fetch_factory 决定。
SUPPORTED_INSTRUMENT_DATASETS: frozenset[Dataset] = (
    default_dataset_registry().supported_instrument_datasets()
)

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
    "SUPPORTED_INSTRUMENT_DATASETS",
    "SWIndustryProvider",
    "get_all_index_codes",
    "get_default_index_codes",
    "get_sw_index_codes",
]
