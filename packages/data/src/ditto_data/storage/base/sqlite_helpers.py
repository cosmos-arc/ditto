"""SQLite 写入准备辅助函数."""

from __future__ import annotations

import polars as pl


def prepare_for_write(df: pl.DataFrame) -> pl.DataFrame:
    """
    准备写入：归一化日期列并排序.

    将 trade_date 列统一为字符串格式（YYYY-MM-DD），
    并按 instrument_id / trade_date 排序，确保写入数据的一致性。

    Args:
        df: 输入 DataFrame.

    Returns:
        归一化并排序后的 DataFrame.

    """
    # 归一化日期列
    if "trade_date" in df.columns:
        if df["trade_date"].dtype == pl.Date:
            # 转换为字符串
            df = df.with_columns(
                pl.col("trade_date").dt.strftime("%Y-%m-%d").alias("trade_date")
            )
        elif df["trade_date"].dtype != pl.String:
            df = df.with_columns(pl.col("trade_date").cast(pl.String))

    # 排序
    return df.sort(["instrument_id", "trade_date"])
