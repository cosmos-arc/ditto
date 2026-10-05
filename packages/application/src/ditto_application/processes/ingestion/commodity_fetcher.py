"""
商品数据获取 — FRED/Tushare 双源逻辑.

从 ``IngestionCoordinator._fetch_commodity_daily`` 提取。
数据源分配：
- FRED: WTI 原油、布伦特原油、VIX
- Tushare: 黄金、白银（FXCM XAU/XAG bid，见 metal adapter 身份说明）
- Sina: 外盘连续期货参考（CL/GC/SI 小白名单，#436；免费无 SLA，
  失败按同一完整性合同显式报错，不静默）

完整性合同（#432）：复合源的任一**已配置**腿失败时整体抛错（分区标记
FAIL 而非 COMPLETE），不允许"只剩金银/只剩油"的批次被报完整；跨市场
参考数据进入策略/Agent 输入的边界由消费侧（market_context）落实。
合法空（周末/节假日无观察行）不是失败：腿成功返回空帧照常合并。
"""

from __future__ import annotations

from typing import Protocol

import polars as pl
from ditto_data.models import (
    METAL_CODE_ALIASES,
    SINA_FOREIGN_FUTURES,
    VIX_CODE_TO_INSTRUMENT_ID,
)
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
    sina_source: CommoditySource | None = None,
) -> pl.DataFrame:
    """
    获取商品数据（原油、贵金属、VIX、外盘连续参考）并合并.

    Args:
        trade_date: 交易日期 (YYYY-MM-DD).
        primary_source: 主数据源（贵金属）.
        fred_source: FRED 数据源（原油/VIX），可选.
        sina_source: 新浪外盘连续期货源，可选（#436）.

    Returns:
        合并后的商品数据 DataFrame.

    Raises:
        Exception: 任一已配置腿失败时原样上抛（见模块完整性合同）。

    """
    return fetch_commodity_range(
        trade_date,
        trade_date,
        primary_source=primary_source,
        fred_source=fred_source,
        sina_source=sina_source,
    )


def fetch_commodity_range(
    start_date: str,
    end_date: str,
    *,
    primary_source: _MetalSource,
    fred_source: CommoditySource | None = None,
    sina_source: CommoditySource | None = None,
) -> pl.DataFrame:
    """
    Fetch commodity observations for one explicit provider interval.

    已配置腿失败即抛错：复合源缺腿不得被标记为完整分区（#432）。
    """
    results: list[pl.DataFrame] = []

    fred_codes = [
        "COMMOD_WTI",
        "COMMOD_BRENT",
        *list(VIX_CODE_TO_INSTRUMENT_ID.keys()),
    ]

    if fred_source is not None:
        # 不吞异常：油/VIX 腿失败时整体失败，防止"只剩金银"被报 COMPLETE。
        fred_df = fred_source.fetch_commodities(
            codes=fred_codes,
            start_date=start_date,
            end_date=end_date,
        )
        logger.info(
            "FRED commodity fetch complete",
            event="fred_commodity_fetch_complete",
            rows=fred_df.height,
        )
        if not fred_df.is_empty():
            results.append(fred_df)
    else:
        logger.warning(
            "FRED source not configured, skipping oil/VIX data",
            event="fred_not_configured",
        )

    if sina_source is not None:
        # 不吞异常：新浪腿失败时整体失败（免费无 SLA，故障必须显式报告，
        # 不得静默降级；#436）。端点无窗口参数，源侧全量返回后本地过滤。
        sina_df = sina_source.fetch_commodities(
            codes=list(SINA_FOREIGN_FUTURES),
            start_date=start_date,
            end_date=end_date,
        )
        logger.info(
            "Sina commodity fetch complete",
            event="sina_commodity_fetch_complete",
            rows=sina_df.height,
        )
        if not sina_df.is_empty():
            results.append(sina_df)

    metal_codes = list(dict.fromkeys(METAL_CODE_ALIASES.values()))

    # 不吞异常：金属腿失败时整体失败，防止"只剩油/VIX"被报 COMPLETE。
    metal_df = primary_source.fetch_metal_daily(
        codes=metal_codes,
        start_date=start_date,
        end_date=end_date,
    )
    if not metal_df.is_empty():
        results.append(metal_df)

    if not results:
        return pl.DataFrame()
    return pl.concat(results)
