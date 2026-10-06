"""
复权计算纯函数模块。

包含 QFQ/HFQ 公式实现，可独立测试。

因子缺失 fail-closed（#514）：行情行关联不到复权因子（行级 join miss
或整个窗口无因子）时抛 :class:`AdjustmentFactorMissingError`，不再
coalesce 1.0 静默退化为未复权价格——那会让 hfq/qfq 收益失真且无告警
（510050/150001/920xxx 因子缺失案例）。消费方需要未复权价格时应显式
请求 raw/adj=none。
"""

from __future__ import annotations

from datetime import date

import polars as pl

from ditto_data.helpers.pit import (
    filter_by_knowledge_date,
    parse_asof_date,
)

_SAMPLE_LIMIT = 5


class AdjustmentFactorMissingError(ValueError):
    """复权因子缺失——复权计算拒绝产出失真值（fail closed）."""


def _reject_missing_adjustment(
    df: pl.DataFrame,
    *,
    check_baseline: bool = False,
) -> None:
    """
    Raise when any joined row lacks an adjustment factor.

    行级缺失 = (instrument_id, trade_date) 行关联不到因子；baseline 缺失
    （仅 qfq）= 标的在 baseline 中完全没有因子，latest_factor 为 null。
    PIT 语义下（PIT contract）缺失 cutoff/可见数据即为错误，回退不安全。
    """
    missing_rows = df.filter(pl.col("adj_factor").is_null())
    if missing_rows.height:
        sample = sorted(
            {
                f"{inst}@{day}"
                for inst, day in missing_rows.select(
                    "instrument_id", "trade_date"
                ).iter_rows()
            }
        )
        instruments = sorted(missing_rows["instrument_id"].unique().to_list())
        raise AdjustmentFactorMissingError(
            f"adj_factor missing for {missing_rows.height} bar row(s) "
            + f"(instruments: {instruments}); "
            + f"sample: {sample[:_SAMPLE_LIMIT]} — refusing to emit unadjusted "
            + "prices as adjusted (#514)"
        )
    if check_baseline:
        missing_baseline = df.filter(pl.col("latest_factor").is_null())
        if missing_baseline.height:
            instruments = sorted(missing_baseline["instrument_id"].unique().to_list())
            raise AdjustmentFactorMissingError(
                "latest_factor missing (no factor rows in the qfq baseline "
                + f"window) for instruments: {instruments} — refusing to emit "
                + "unadjusted prices as adjusted (#514)"
            )


def apply_qfq_adj(
    df: pl.DataFrame,
    adj_df: pl.DataFrame,
    asof: date | str | None = None,
) -> pl.DataFrame:
    """
    应用前复权（QFQ）调整。

    Tushare QFQ: adj_price = orig_price * cur_factor / latest_factor。

    如果提供 asof，baseline (latest_factor) 将基于 asof 日期之前的因子计算。

    注意：pre_close 字段不需要复权调整
    - Tushare 返回的 pre_close 已经是除权参考价（已处理除权除息）
    - 只对 open/high/low/close 进行复权（这些是原始价格）
    - pre_close 保持原样即可，当日涨跌幅计算已正确

    Raises:
        AdjustmentFactorMissingError: 任一行关联不到因子，或标的在
            baseline 窗口内完全没有因子（fail closed，#514）。

    Args:
        df: 已关联 adj_factor 的 K线数据。
        adj_df: 调整因子数据（已排序，包含所有因子）。
        asof: Point-in-Time 日期（date 对象或字符串）。
            如果提供，baseline 计算将使用该日期之前的因子。

    Returns:
        QFQ 调整后的 DataFrame.

    """
    # 计算 baseline：如果提供了 asof，需要过滤
    if asof is None:
        baseline_df = adj_df
    else:
        # 转换为 date 对象
        pit_dt = parse_asof_date(asof)
        # 过滤 baseline（使用 pit 模块的通用函数）
        baseline_df = filter_by_knowledge_date(
            adj_df, pit_dt, date_column="knowledge_date"
        )

    # 获取每个 Instrument ID 的最新因子（基于 baseline）
    latest_factors = baseline_df.group_by("instrument_id").agg(
        pl.col("adj_factor").last().alias("latest_factor")
    )
    df = df.join(latest_factors, on="instrument_id", how="left")

    _reject_missing_adjustment(df, check_baseline=True)

    # 应用 QFQ 公式
    df = df.with_columns(
        [
            (pl.col("open") * pl.col("adj_factor") / pl.col("latest_factor")).alias(
                "open"
            ),
            (pl.col("high") * pl.col("adj_factor") / pl.col("latest_factor")).alias(
                "high"
            ),
            (pl.col("low") * pl.col("adj_factor") / pl.col("latest_factor")).alias(
                "low"
            ),
            (pl.col("close") * pl.col("adj_factor") / pl.col("latest_factor")).alias(
                "close"
            ),
        ]
    )
    return df.drop(["adj_factor", "latest_factor"])


def apply_hfq_adj(
    df: pl.DataFrame,
    adj_df: pl.DataFrame,
) -> pl.DataFrame:
    """
    应用后复权（HFQ）调整。

    后复权：adj_price = orig_price * cur_factor。

    注意：pre_close 字段不需要复权调整
    - Tushare 返回的 pre_close 已经是除权参考价（已处理除权除息）
    - 只对 open/high/low/close 进行复权（这些是原始价格）
    - pre_close 保持原样即可，当日涨跌幅计算已正确

    Raises:
        AdjustmentFactorMissingError: 任一行关联不到因子（fail closed，#514）。

    Args:
        df: 已关联 adj_factor 的 K线数据。
        adj_df: 调整因子数据（未使用，保持参数一致性）。

    Returns:
        HFQ 调整后的 DataFrame.

    """
    _reject_missing_adjustment(df)

    # 应用 HFQ 公式
    df = df.with_columns(
        [
            (pl.col("open") * pl.col("adj_factor")).alias("open"),
            (pl.col("high") * pl.col("adj_factor")).alias("high"),
            (pl.col("low") * pl.col("adj_factor")).alias("low"),
            (pl.col("close") * pl.col("adj_factor")).alias("close"),
        ]
    )
    return df.drop("adj_factor")
