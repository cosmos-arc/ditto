"""SQLite 写入准备与 JSON 序列化辅助函数."""

from __future__ import annotations

from typing import cast

import orjson
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


def partition_keys_json(partition_keys: tuple[str, ...]) -> str:
    """将分区键元组序列化为 JSON 字符串."""
    return orjson.dumps(list(partition_keys)).decode()


def partition_keys_from_json(value: str) -> tuple[str, ...]:
    """从 JSON 字符串反序列化分区键元组."""
    parsed: object = orjson.loads(value)
    if not isinstance(parsed, list):
        raise ValueError("partition keys must be a JSON string list")
    values = cast(list[object], parsed)
    keys: list[str] = []
    for item in values:
        if not isinstance(item, str):
            raise ValueError("partition keys must be a JSON string list")
        keys.append(item)
    return tuple(keys)
