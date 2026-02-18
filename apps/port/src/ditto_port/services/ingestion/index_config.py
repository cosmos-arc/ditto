"""
指数数据配置模块。

提供市场指数、风格指数的固定配置。
SW 行业指数代码通过 Tushare API 动态获取。

指数分类：
- 市场基准（8个）：大盘趋势判断、市场情绪
- 风格指数（9个）：大小盘/价值成长轮动
- SW 行业指数：申万行业指数，从 Tushare API 动态获取

配置说明：
- 所有代码均为 Tushare source_ticker 格式
- SW 行业指数后缀为 .SI（申万指数交易所代码）
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal, Protocol

if TYPE_CHECKING:
    import polars as pl

__all__ = [
    "MARKET_INDEX_CODES",
    "STYLE_INDEX_CODES",
    "get_default_index_codes",
    "get_sw_index_codes",
]

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
    """
    从 Tushare API 动态获取申万行业指数代码列表.

    Args:
        source: 数据源，需实现 fetch_sw_industry 方法.
        level: 行业级别 (1=一级行业, 2=二级行业).

    Returns:
        SW 行业指数代码列表（Tushare source_ticker 格式）.

    Example:
        >>> from ditto_datahub.sources import TushareSource
        >>> source = TushareSource(settings, token)
        >>> codes = get_sw_index_codes(source, level=1)
        >>> print(codes[:3])
        ['801010.SI', '801020.SI', '801030.SI']

    """
    df = source.fetch_sw_industry(level=level)
    if df.is_empty():
        return []
    return df["source_ticker"].unique().sort().to_list()


def get_default_index_codes(
    include_style: bool = True,
) -> list[str]:
    """
    获取默认指数代码列表（仅固定配置的指数）.

    注意：此函数仅返回硬编码的市场指数和风格指数。
    如需包含 SW 行业指数，请使用 get_sw_index_codes() 动态获取。

    Args:
        include_style: 是否包含风格指数（默认 True）.

    Returns:
        指数代码列表（Tushare source_ticker 格式）。

    """
    codes = list(MARKET_INDEX_CODES)
    if include_style:
        codes.extend(STYLE_INDEX_CODES)
    return codes


def get_all_index_codes(
    source: SWIndustryProvider,
    include_style: bool = True,
    include_sw_levels: list[Literal[1, 2]] | None = None,
) -> list[str]:
    """
    获取所有指数代码列表（包含动态获取的 SW 行业指数）.

    Args:
        source: 数据源，用于动态获取 SW 行业指数代码.
        include_style: 是否包含风格指数（默认 True）.
        include_sw_levels: 要包含的 SW 行业级别列表，默认 [1]（仅一级行业）.

    Returns:
        指数代码列表（Tushare source_ticker 格式）。

    Example:
        >>> from ditto_datahub.sources import TushareSource
        >>> source = TushareSource(settings, token)
        >>> # 获取市场指数 + 风格指数 + SW L1/L2 行业指数
        >>> codes = get_all_index_codes(
        ...     source,
        ...     include_style=True,
        ...     include_sw_levels=[1, 2],
        ... )

    """
    codes = get_default_index_codes(include_style=include_style)

    if include_sw_levels:
        for level in include_sw_levels:
            sw_codes = get_sw_index_codes(source, level=level)
            codes.extend(sw_codes)

    return codes
