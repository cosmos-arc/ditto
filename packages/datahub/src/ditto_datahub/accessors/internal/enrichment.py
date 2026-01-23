"""
数据增强纯函数模块。

提供 DataFrame 的列增强逻辑，纯数据操作，无 side effect。
"""

import polars as pl


def enrich_with_sid(
    df: pl.DataFrame,
    sid_mapping: dict[str, int],
    src_code_col: str = "ts_code",
    source: str = "tushare",
) -> pl.DataFrame:
    """
    使用 sid 映射字典为 DataFrame 添加 sid 列。

    Args:
        df: 输入 DataFrame，必须包含 src_code_col 指定的列。
        sid_mapping: {src_code: sid} 映射字典。
        src_code_col: 源代码列名。
        source: 数据源标识符。

    Returns:
        添加了 sid 和 source 列的 DataFrame。

    """
    src_codes = df[src_code_col].to_list()
    sids = [sid_mapping.get(code) for code in src_codes]

    return df.with_columns(
        pl.Series(sids, dtype=pl.Int32).alias("sid"),
        pl.lit(source).alias("source"),
    )


def enrich_with_symbol(
    df: pl.DataFrame,
    symbol_map: pl.DataFrame,
) -> pl.DataFrame:
    """
    使用 symbol 映射表为 DataFrame 添加 symbol 列。

    Args:
        df: 输入 DataFrame，必须包含 sid 列。
        symbol_map: symbol 映射表，包含 sid 和 symbol 列。

    Returns:
        添加了 symbol 列的 DataFrame。

    """
    if "sid" not in df.columns or df.is_empty():
        return df

    return df.join(symbol_map, on="sid", how="left")


def enrich_with_status(
    df: pl.DataFrame,
    status_df: pl.DataFrame,
    on: list[str] | None = None,
) -> pl.DataFrame:
    """
    使用状态数据表为 DataFrame 添加状态列。

    Args:
        df: 输入 DataFrame（通常包含 sid 和 trade_date）。
        status_df: 状态数据表，包含 is_suspended, is_st, st_type, list_status 等列。
        on: 连接键，默认 ["sid", "trade_date"]。

    Returns:
        添加了状态列的 DataFrame，缺失值填充为默认值。

    """
    if df.is_empty():
        return df

    join_keys = on or ["sid", "trade_date"]

    # Select only status columns
    status_cols = [
        "sid",
        "trade_date",
        "is_suspended",
        "suspend_timing",
        "is_st",
        "st_type",
        "list_status",
    ]
    status_to_join = status_df.select(
        [c for c in status_cols if c in status_df.columns]
    )

    result = df.join(status_to_join, on=join_keys, how="left")

    # Fill null values with defaults
    return result.with_columns(
        pl.col("is_suspended").fill_null(False),
        pl.col("suspend_timing").fill_null(""),
        pl.col("is_st").fill_null(False),
        pl.col("st_type").fill_null(""),
        pl.col("list_status").fill_null("L"),
    )
