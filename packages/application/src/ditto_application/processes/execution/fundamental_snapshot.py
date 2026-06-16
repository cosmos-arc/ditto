"""
基本面快照 — PIT 查询 + 因子列预计算，注入回测 DataFeed 的数据通道闭包.

回测路径需要个股基本面因子列（roe / net_margin / eps 等）注入 market_data，
使因子表达式（quality_roe → "roe" → pl.col("roe")）能读到列。

架构边界：
  - backtest 的 ``ProviderBackedDataFeed`` 只做数据通道（委托 Callable），
    不含 PIT 查询 / 因子计算 / maturity gate 业务逻辑。
  - 本模块在 application processes 层，封装：
      1. 经 FundamentalQueryFacade 做 PIT 查询（gate 经 allow_experimental_data）
      2. 从 storage 原始列（net_profit / net_assets / revenue / eps）预计算因子列
  - 返回的 ``FundamentalSnapshotFn`` 闭包被注入 ProviderBackedDataFeed。
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import date
from typing import Protocol

import polars as pl
from ditto_kernel.identity import InstrumentId

__all__ = [
    "FundamentalReadFacade",
    "FundamentalSnapshotFn",
    "build_fundamental_snapshot_fn",
]

# 与 ditto_backtest.data_feed.FundamentalSnapshotFn 同型（结构相等）。
# 不跨层 import 以避免 application processes 反向依赖 backtest 类型别名。
FundamentalSnapshotFn = Callable[[Sequence[InstrumentId], date], pl.DataFrame]

# 快照 schema：instrument_id + 预计算因子列。pe_ratio 依赖 close（截面价），
# 由 build_factor_bundle 在 merge 市场数据后补算，故本快照不产出 pe_ratio。
_EMPTY_SCHEMA: dict[str, type[pl.DataType]] = {
    "instrument_id": pl.Int64,
    "roe": pl.Float64,
    "net_margin": pl.Float64,
    "eps": pl.Float64,
}

_SCHEMA_OVERRIDES: dict[str, type[pl.DataType]] = {
    "instrument_id": pl.Int64,
    "roe": pl.Float64,
    "net_margin": pl.Float64,
    "eps": pl.Float64,
}


class FundamentalReadFacade(Protocol):
    """
    回测路径所需的基本面读取能力（FundamentalQueryFacade 满足此 Protocol）.

    定义在 application processes 层，使 builders（service_factory）能依赖此 Protocol
    而不 import queries（规避 R8 builders→queries 禁令）。
    """

    def get_balance_sheet(
        self,
        instrument_id: int,
        as_of_date: date,
        *,
        allow_experimental_data: bool = False,
    ) -> pl.DataFrame | None:
        """查询资产负债表（PIT，maturity gate 经 allow_experimental_data）."""
        ...

    def get_income_statement(
        self,
        instrument_id: int,
        as_of_date: date,
        *,
        allow_experimental_data: bool = False,
    ) -> pl.DataFrame | None:
        """查询利润表（PIT，maturity gate 经 allow_experimental_data）."""
        ...


def build_fundamental_snapshot_fn(
    facade: FundamentalReadFacade,
    *,
    allow_experimental_data: bool,
) -> FundamentalSnapshotFn:
    """
    构造基本面快照闭包.

    Args:
        facade: 基本面读取 facade（FundamentalQueryFacade 满足 Protocol）。
        allow_experimental_data: 透传给 facade 的 maturity gate opt-in
            （balance_sheet / income_statement 为 experimental dataset）。

    Returns:
        ``FundamentalSnapshotFn`` 闭包：接收 (instrument_ids, as_of_date)，
        返回含 ``instrument_id / roe / net_margin / eps`` 列的截面 DataFrame。
        PIT as_of 由调用方传 ``knowledge_date``；缺数据/除零返回 null。

    预计算规则（storage 列 → 因子列）:
        - roe = net_profit / net_assets（net_profit←income，net_assets←balance）
        - net_margin = net_profit / revenue（均来自 income）
        - eps = income.eps（透传，供 build_factor_bundle 算 pe_ratio = close / eps）

    """

    def _snapshot(
        instrument_ids: Sequence[InstrumentId],
        as_of_date: date,
    ) -> pl.DataFrame:
        if not instrument_ids:
            return pl.DataFrame(schema=_EMPTY_SCHEMA)

        rows: list[dict[str, float | int | None]] = []
        for iid in instrument_ids:
            iid_int = int(iid)
            # PIT 查询：as_of_date 由调用方传 knowledge_date
            bs = facade.get_balance_sheet(
                iid_int,
                as_of_date,
                allow_experimental_data=allow_experimental_data,
            )
            inc = facade.get_income_statement(
                iid_int,
                as_of_date,
                allow_experimental_data=allow_experimental_data,
            )

            net_assets = _first_float(bs, "net_assets")
            net_profit = _first_float(inc, "net_profit")
            revenue = _first_float(inc, "revenue")
            eps = _first_float(inc, "eps")

            roe = _safe_div(net_profit, net_assets)
            net_margin = _safe_div(net_profit, revenue)

            rows.append(
                {
                    "instrument_id": iid_int,
                    "roe": roe,
                    "net_margin": net_margin,
                    "eps": eps,
                },
            )

        return pl.DataFrame(rows, schema_overrides=_SCHEMA_OVERRIDES)

    return _snapshot


def _first_float(df: pl.DataFrame | None, col: str) -> float | None:
    """安全取 DataFrame 首行某列的 float 值；None / 空 / 缺列返回 None."""
    if df is None or df.is_empty() or col not in df.columns:
        return None
    value = df[col][0]
    return float(value) if value is not None else None


def _safe_div(numerator: float | None, denominator: float | None) -> float | None:
    """安全除法；任一为 None 或分母为零返回 None."""
    if numerator is None or denominator is None or denominator == 0:
        return None
    return numerator / denominator
