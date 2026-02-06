"""
复权计算纯函数模块。

包含 QFQ/HFQ 公式实现，可独立测试。
"""

from datetime import date

import polars as pl

from ditto_datahub.helpers.pit import (
    filter_by_knowledge_date,
    parse_asof_date,
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

    # 获取每个 SID 的最新因子（基于 baseline）
    latest_factors = baseline_df.group_by("sid").agg(
        pl.col("adj_factor").last().alias("latest_factor")
    )
    df = df.join(latest_factors, on="sid", how="left")

    # 应用 QFQ 公式，缺失值使用 1.0（返回原始价格）
    df = df.with_columns(
        [
            (
                pl.col("open")
                * pl.coalesce("adj_factor", 1.0)
                / pl.coalesce("latest_factor", 1.0)
            ).alias("open"),
            (
                pl.col("high")
                * pl.coalesce("adj_factor", 1.0)
                / pl.coalesce("latest_factor", 1.0)
            ).alias("high"),
            (
                pl.col("low")
                * pl.coalesce("adj_factor", 1.0)
                / pl.coalesce("latest_factor", 1.0)
            ).alias("low"),
            (
                pl.col("close")
                * pl.coalesce("adj_factor", 1.0)
                / pl.coalesce("latest_factor", 1.0)
            ).alias("close"),
        ]
    )
    return df.drop(["adj_factor", "latest_factor"])


def apply_hfq_adj(
    df: pl.DataFrame,
    adj_df: pl.DataFrame,
) -> pl.DataFrame:
    """
    应用后复权（HFQ）调整。

    后复权：adj_price = orig_price * cur_factor
    缺失值使用 1.0（返回原始价格）。

    注意：pre_close 字段不需要复权调整
    - Tushare 返回的 pre_close 已经是除权参考价（已处理除权除息）
    - 只对 open/high/low/close 进行复权（这些是原始价格）
    - pre_close 保持原样即可，当日涨跌幅计算已正确

    Args:
        df: 已关联 adj_factor 的 K线数据。
        adj_df: 调整因子数据（未使用，保持参数一致性）。

    Returns:
        HFQ 调整后的 DataFrame.

    """
    # 应用 HFQ 公式，缺失值使用 1.0
    df = df.with_columns(
        [
            (pl.col("open") * pl.coalesce("adj_factor", 1.0)).alias("open"),
            (pl.col("high") * pl.coalesce("adj_factor", 1.0)).alias("high"),
            (pl.col("low") * pl.coalesce("adj_factor", 1.0)).alias("low"),
            (pl.col("close") * pl.coalesce("adj_factor", 1.0)).alias("close"),
        ]
    )
    return df.drop("adj_factor")
