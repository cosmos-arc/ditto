"""
SQLite 数据合并与插入逻辑.

提供去重合并（merge）和 INSERT SQL 构建两大能力，
由 SQLiteStore 在 write_dataframe 流程中调用。
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

import polars as pl
from ditto_platform.foundation import OnDuplicate


def merge_data(
    new_df: pl.DataFrame,
    existing_df: pl.DataFrame,
    on_duplicate: OnDuplicate,
) -> tuple[pl.DataFrame, int, int]:
    """
    合并新数据与现有数据.

    根据 on_duplicate 策略处理 instrument_id + trade_date 键冲突：
    - ERROR: 检测到重复即抛出 ValueError
    - KEEP_FIRST: 保留现有数据，丢弃新数据中的重复行
    - KEEP_LAST: 新数据覆盖现有数据（Last-Write-Wins）

    Args:
        new_df: 新数据.
        existing_df: 现有数据.
        on_duplicate: 重复数据处理策略.

    Returns:
        (合并后的 DataFrame, 新增行数, 更新行数).

    Raises:
        ValueError: 如果 on_duplicate=ERROR 且存在重复数据.

    """
    key_columns = ["instrument_id", "trade_date"]

    # 检测重复数据
    existing_keys = existing_df.select(key_columns)
    new_keys = new_df.select(key_columns)

    # 找出重叠的键
    merged_keys = existing_keys.join(new_keys, on=key_columns, how="inner")
    overlap_count = len(merged_keys)

    added = 0
    updated = 0

    if not merged_keys.is_empty():
        # 存在重复数据
        if on_duplicate == OnDuplicate.ERROR:
            msg = (
                f"Duplicate data: {overlap_count} overlapping key pairs. "
                "Use on_duplicate='keep_first' to preserve, or "
                "on_duplicate='keep_last' to overwrite."
            )
            raise ValueError(msg)
        elif on_duplicate == OnDuplicate.KEEP_FIRST:
            # 保留现有数据，过滤掉新数据中的重复部分
            non_overlapping = new_keys.join(existing_keys, on=key_columns, how="anti")
            new_df = new_df.join(non_overlapping, on=key_columns, how="inner")
            combined = pl.concat([existing_df, new_df])
            added = len(new_df)
            updated = 0
        elif on_duplicate == OnDuplicate.KEEP_LAST:
            # Last-Write-Wins: 新数据覆盖现有数据
            combined = pl.concat([existing_df, new_df])
            combined = combined.unique(subset=key_columns, keep="last")
            # 新增 = 新数据中去重后的行数
            # 更新 = 重叠的行数
            added = len(new_df) - overlap_count
            updated = overlap_count
        else:
            msg = f"Unknown OnDuplicate strategy: {on_duplicate}"
            raise ValueError(msg)
    else:
        # 无重复，直接合并
        combined = pl.concat([existing_df, new_df])
        added = len(new_df)
        updated = 0

    return combined, added, updated


def build_insert_sql(
    table: str,
    columns: list[str],
    on_duplicate: OnDuplicate,
) -> str:
    """
    根据去重策略构建 INSERT SQL 语句.

    Args:
        table: 目标表名.
        columns: 列名列表.
        on_duplicate: 重复数据处理策略.

    Returns:
        构建好的 SQL 语句字符串.

    Raises:
        ValueError: 如果 on_duplicate 策略无效.

    """
    placeholders = ",".join(["?"] * len(columns))
    col_names = ",".join(f'"{col}"' for col in columns)

    if on_duplicate == OnDuplicate.KEEP_LAST:
        # INSERT OR REPLACE：删除旧记录，插入新记录
        return (
            f'INSERT OR REPLACE INTO "{table}" ({col_names}) '  # noqa: S608 - table 是受控的表名，参数使用占位符
            f"VALUES ({placeholders})"
        )
    elif on_duplicate == OnDuplicate.KEEP_FIRST:
        # INSERT OR IGNORE：忽略重复记录
        return (
            f'INSERT OR IGNORE INTO "{table}" ({col_names}) '  # noqa: S608 - table 是受控的表名，参数使用占位符
            f"VALUES ({placeholders})"
        )
    elif on_duplicate == OnDuplicate.ERROR:
        # 直接 INSERT：遇到重复会报错
        return (
            f'INSERT INTO "{table}" ({col_names}) '  # noqa: S608 - table 是受控的表名，参数使用占位符
            f"VALUES ({placeholders})"
        )
    else:
        msg = f"Unknown OnDuplicate strategy: {on_duplicate}"
        raise ValueError(msg)


def insert_dataframe(
    table: str,
    df: pl.DataFrame,
    on_duplicate: OnDuplicate,
    executemany_fn: Callable[[str, Sequence[Sequence[Any] | tuple[Any, ...]]], object],
    commit_fn: Callable[[], None],
) -> None:
    """
    插入 DataFrame 到表.

    通过回调函数执行 SQL，保持与 SQLiteStore 的解耦。

    Args:
        table: 表名.
        df: 要插入的 DataFrame.
        on_duplicate: 重复数据处理策略.
        executemany_fn: 批量执行 SQL 的回调（SQLiteStore.executemany）.
        commit_fn: 提交事务的回调（SQLiteStore.commit）.

    """
    sql = build_insert_sql(table, df.columns, on_duplicate)
    rows = df.rows()
    executemany_fn(sql, rows)
    commit_fn()
