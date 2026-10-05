"""
复权因子跨源对账推导 — 事件流 vs 累积因子的同基准比例（#438）.

fuyao adjustment-factors 是公司行动事件（分红/送转/配股），Tushare adj_factor
是每日累积因子：两者不比较绝对数值（基期可能不同），比较同基准相邻比例——
主源侧 ``F(D)/F(prev)``，事件侧 ``prev_close / 除权参考价``（上交所除权参考价
公式 ``(prev_close - 每股分红 + 配股比例×配股价) / (1 + 每股送转 + 配股比例)``，
前收取主源同基准收盘，不用辅源自身价格）。

缺前价、缺配股价或空事件不可推导：行保留并标记 ``underivable_reason``，
单列报告，不伪造匹配；无法等价的比例差异由通用 CrossSourceChecker 按
``adjustment_ratio`` 字段容差比较。
"""

from __future__ import annotations

from datetime import date
from typing import Literal

import polars as pl

__all__ = [
    "EVENT_VALUE_COLUMNS",
    "derive_event_adjustment_ratios",
    "derive_factor_ratios",
]

# 稀疏事件流：不适用的分量为 null，按 0 参与公式（§ #438 裁决）
EVENT_VALUE_COLUMNS = (
    "dividend_per_share",
    "per_share_bonus",
    "allotment_ratio",
    "allotment_price",
)

type UnderivableReason = Literal[
    "empty_event",
    "missing_prev_close",
    "missing_allotment_price",
    "non_positive_reference_price",
]

# 比例与 1 的差小于该值视为未变化（主侧无除权事件）
_FACTOR_RATIO_EPSILON = 1e-9

_EVENT_RATIO_SCHEMA: dict[str, type[pl.DataType]] = {
    "instrument_id": pl.Int64,
    "trade_date": pl.Date,
    "dividend_per_share": pl.Float64,
    "per_share_bonus": pl.Float64,
    "allotment_ratio": pl.Float64,
    "allotment_price": pl.Float64,
    "adjustment_ratio": pl.Float64,
    "event_kind": pl.String,
    "underivable_reason": pl.String,
}


def _empty_factor_ratio_frame() -> pl.DataFrame:
    return pl.DataFrame(
        schema={
            "instrument_id": pl.Int64,
            "trade_date": pl.Date,
            "adjustment_ratio": pl.Float64,
        }
    )


def derive_factor_ratios(factor_window: pl.DataFrame, trade_date: date) -> pl.DataFrame:
    """
    主源累积因子 → 当日相对前值的调整比例（仅保留发生变化的行）.

    Args:
        factor_window: [instrument_id, trade_date, adj_factor]，含目标日与
            此前回看窗（复用 #395 除权日来源的 40 日窗口约定）.
        trade_date: 对账目标日 D.

    Returns:
        [instrument_id, trade_date, adjustment_ratio]；D 无因子或窗内无前值
        的标的不产生行（无前值 = 主侧不可推导，按主侧缺席计入未匹配）.

    """
    required = {"instrument_id", "trade_date", "adj_factor"}
    if factor_window.is_empty() or not required.issubset(factor_window.columns):
        return _empty_factor_ratio_frame()
    frame = factor_window.select(*required)
    if frame["trade_date"].dtype == pl.String:
        frame = frame.with_columns(pl.col("trade_date").str.to_date())
    target = frame.filter(pl.col("trade_date") == trade_date)
    previous_latest = (
        frame.filter(pl.col("trade_date") < trade_date)
        .sort("trade_date")
        .group_by("instrument_id")
        .agg(pl.col("adj_factor").last().alias("prev_factor"))
    )
    changed = (
        target.join(previous_latest, on="instrument_id", how="inner")
        .select(
            "instrument_id",
            trade_date=pl.lit(trade_date, dtype=pl.Date),
            adjustment_ratio=pl.col("adj_factor") / pl.col("prev_factor"),
        )
        .filter((pl.col("adjustment_ratio") - 1.0).abs() > _FACTOR_RATIO_EPSILON)
    )
    return changed


def derive_event_adjustment_ratios(
    events: pl.DataFrame,
    prev_closes: pl.DataFrame,
) -> pl.DataFrame:
    """
    事件帧 + 主源前收 → 事件可推导的调整比例；不可推导行保留原因.

    Args:
        events: [instrument_id, trade_date, *EVENT_VALUE_COLUMNS]（经身份
            反解的辅源事件，ex_date 已映射为 trade_date）.
        prev_closes: [instrument_id, prev_close]（主源同基准前收）.

    Returns:
        events 各列 + [adjustment_ratio, event_kind, underivable_reason]；
        ``event_kind`` ∈ dividend/bonus/allotment/complex（分红/送转/配股
        单列口径），不可推导行 ``adjustment_ratio`` 为 null.

    """
    if events.is_empty():
        return pl.DataFrame(schema=_EVENT_RATIO_SCHEMA)

    dividend = pl.col("dividend_per_share").fill_null(0.0)
    bonus = pl.col("per_share_bonus").fill_null(0.0)
    allotment = pl.col("allotment_ratio").fill_null(0.0)
    has_dividend = dividend > 0
    has_bonus = bonus > 0
    has_allotment = allotment > 0
    kind = (
        pl.when(
            (has_dividend & has_bonus)
            | (has_dividend & has_allotment)
            | (has_bonus & has_allotment)
        )
        .then(pl.lit("complex"))
        .when(has_dividend)
        .then(pl.lit("dividend"))
        .when(has_bonus)
        .then(pl.lit("bonus"))
        .when(has_allotment)
        .then(pl.lit("allotment"))
        .otherwise(pl.lit("empty"))
    )

    closes = prev_closes.select("instrument_id", "prev_close")
    # 配股价按 0 参与公式：allotment>0 且缺价已由 reason 前置判为不可推导，
    # ratio 被守卫置 null；否则 0×null 的空值传播会污染无关事件的参考价。
    allotment_price = pl.col("allotment_price").fill_null(0.0)
    reference_price = (
        pl.col("prev_close") - dividend + allotment * allotment_price
    ) / (1.0 + bonus + allotment)
    reason = (
        pl.when(kind == pl.lit("empty"))
        .then(pl.lit("empty_event"))
        .when(pl.col("prev_close").is_null())
        .then(pl.lit("missing_prev_close"))
        .when(has_allotment & pl.col("allotment_price").is_null())
        .then(pl.lit("missing_allotment_price"))
        .when((reference_price.is_not_null()) & (reference_price <= 0))
        .then(pl.lit("non_positive_reference_price"))
        .otherwise(None)
        .cast(pl.String)
    )
    ratio = (
        pl.when(reason.is_null() & reference_price.is_not_null())
        .then(pl.col("prev_close") / reference_price)
        .otherwise(None)
    )

    return (
        events.join(closes, on="instrument_id", how="left")
        .with_columns(
            adjustment_ratio=ratio,
            event_kind=kind,
            underivable_reason=reason,
        )
        .drop("prev_close")
    )
