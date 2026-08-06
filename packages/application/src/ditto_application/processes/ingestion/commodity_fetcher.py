"""
商品数据获取 — FRED/Tushare 双源逻辑.

从 ``IngestionCoordinator._fetch_commodity_daily`` 提取。
数据源分配：
- FRED: WTI 原油、布伦特原油、VIX
- Tushare: 黄金、白银（FRED 数据已停止更新）
"""

from __future__ import annotations

from typing import Protocol

import polars as pl
from ditto_data.models import METAL_CODE_ALIASES, VIX_CODE_TO_INSTRUMENT_ID
from ditto_platform.foundation import logger


class _MetalSource(Protocol):
    """Minimized protocol for metal data fetching."""

    def fetch_metal_daily(
        self,
        codes: list[str],
        start_date: str,
        end_date: str,
    ) -> pl.DataFrame: ...


class CommoditySource(Protocol):
    """Minimized protocol for commodity data fetching."""

    def fetch_commodities(
        self,
        codes: list[str],
        start_date: str,
        end_date: str,
    ) -> pl.DataFrame: ...


__all__ = ["fetch_commodity_daily", "fetch_commodity_range"]


def fetch_commodity_daily(
    trade_date: str,
    *,
    primary_source: _MetalSource,
    fred_source: CommoditySource | None = None,
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
    return fetch_commodity_range(
        trade_date,
        trade_date,
        primary_source=primary_source,
        fred_source=fred_source,
    )


def fetch_commodity_range(
    start_date: str,
    end_date: str,
    *,
    primary_source: _MetalSource,
    fred_source: CommoditySource | None = None,
) -> pl.DataFrame:
    """Fetch commodity observations for one explicit provider interval."""
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
                start_date=start_date,
                end_date=end_date,
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
            start_date=start_date,
            end_date=end_date,
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
