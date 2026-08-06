"""
Macro/FX/Metal/Commodity 数据获取 — 从 TushareSource 提取的宏观/外汇/金属 fetch 逻辑.

提供 fetch_macro_indicators / fetch_fx_daily / fetch_metal_daily /
fetch_commodities 模块级函数，
供 TushareSource 的同名方法委托调用。
"""

from __future__ import annotations

import polars as pl

from ditto_data.sources.tushare.adapters.fx import FxTushareAdapter
from ditto_data.sources.tushare.adapters.macro import MacroTushareAdapter
from ditto_data.sources.tushare.adapters.metal import MetalTushareAdapter


def fetch_macro_indicators(
    macro: MacroTushareAdapter,
    trade_date: str,
) -> pl.DataFrame:
    """Fetch macro indicators data."""
    return macro.fetch_macro_indicators(trade_date)


def fetch_macro_indicators_range(
    macro: MacroTushareAdapter,
    start_date: str,
    end_date: str,
) -> pl.DataFrame:
    """Fetch normalized macro observations over one bounded interval."""
    return macro.fetch_macro_indicators_range(start_date, end_date)


def fetch_fx_daily(
    fx: FxTushareAdapter,
    *,
    ts_codes: list[str],
    start_date: str,
    end_date: str,
) -> pl.DataFrame:
    """
    Fetch FX daily data from Tushare.

    Args:
        fx: FX 数据适配器.
        ts_codes: FX ticker codes (e.g., ["USDCNH.FXCM"]).
        start_date: Start date (YYYY-MM-DD).
        end_date: End date (YYYY-MM-DD).

    Returns:
        DataFrame with FX_SOURCE_SCHEMA columns.

    """
    return fx.fetch_fx_daily(
        ts_codes=ts_codes,
        start_date=start_date,
        end_date=end_date,
    )


def fetch_metal_daily(
    metal: MetalTushareAdapter,
    *,
    codes: list[str],
    start_date: str,
    end_date: str,
) -> pl.DataFrame:
    """
    Fetch precious metals daily data from Tushare fx_daily API.

    使用 fx_daily 接口的 METAL 分类获取贵金属数据（黄金、白银）。

    Args:
        metal: Metal 数据适配器.
        codes: Metal codes (e.g., ["XAUUSD.FXCM", "COMMOD_GOLD"]).
               支持别名：COMMOD_GOLD, GOLD, XAUUSD, COMMOD_SILVER, SILVER, XAGUSD
        start_date: Start date (YYYY-MM-DD).
        end_date: End date (YYYY-MM-DD).

    Returns:
        DataFrame with COMMODITY_SOURCE_SCHEMA columns.

    """
    return metal.fetch_metal_daily(
        codes=codes,
        start_date=start_date,
        end_date=end_date,
    )


def fetch_commodities(
    codes: list[str],
    start_date: str,
    end_date: str,
) -> pl.DataFrame:
    """Tushare 不支持商品数据。"""
    raise NotImplementedError("Tushare does not support commodity data")
