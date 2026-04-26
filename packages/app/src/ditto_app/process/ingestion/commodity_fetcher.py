"""
商品数据获取 — FRED/Tushare 双源逻辑.

从 ``IngestionCoordinator._fetch_commodity_daily`` 提取。
数据源分配：
- FRED: WTI 原油、布伦特原油、VIX
- Tushare: 黄金、白银（FRED 数据已停止更新）
"""

from __future__ import annotations

import polars as pl
from ditto_data.models import METAL_CODE_ALIASES, VIX_CODE_TO_INSTRUMENT_ID
from ditto_data.sources.protocols import CommodityFetcher, MacroFetcher
from ditto_infra.foundation import logger

__all__ = ["fetch_commodity_daily"]


def fetch_commodity_daily(
    trade_date: str,
    *,
    primary_source: MacroFetcher,
    fred_source: CommodityFetcher | None = None,
) -> pl.DataFrame:
    """
    获取商品数据（原油、贵金属、VIX）并合并.

    Args:
        trade_date: 交易日期 (YYYY-MM-DD).
        primary_source: 主数据源（贵金属）.
        fred_source: FRED 数据源（原油/VIX），可选.

    Returns:
        合并后的商品数据 DataFrame.

    """
    results: list[pl.DataFrame] = []

    fred_codes = [
        "COMMOD_WTI",
        "COMMOD_BRENT",
        *list(VIX_CODE_TO_INSTRUMENT_ID.keys()),
    ]

    if fred_source is not None:
        try:
            fred_df = fred_source.fetch_commodities(
                codes=fred_codes,
                start_date=trade_date,
                end_date=trade_date,
            )
            if not fred_df.is_empty():
                results.append(fred_df)
        except Exception as e:
            logger.warning(
                "FRED commodity fetch failed, continuing with Tushare metals",
                event="fred_commodity_fetch_failed",
                error=str(e),
            )
    else:
        logger.warning(
            "FRED source not configured, skipping oil/VIX data",
            event="fred_not_configured",
        )

    metal_codes = list(dict.fromkeys(METAL_CODE_ALIASES.values()))

    try:
        metal_df = primary_source.fetch_metal_daily(
            codes=metal_codes,
            start_date=trade_date,
            end_date=trade_date,
        )
        if not metal_df.is_empty():
            results.append(metal_df)
    except Exception as e:
        logger.warning(
            "Tushare metal fetch failed",
            event="tushare_metal_fetch_failed",
            error=str(e),
        )

    if not results:
        return pl.DataFrame()
    return pl.concat(results)
