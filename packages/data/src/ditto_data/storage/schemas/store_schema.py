"""StoreSchema: 存储格式定义."""

from __future__ import annotations

from dataclasses import dataclass

import polars as pl


@dataclass(frozen=True)
class StoreSchema:
    """
    存储格式定义.

    定义存储到 Parquet 文件的列结构和类型.

    Attributes:
        dataset: 数据集标识 (如 "market/stock/bars")
        key_columns: 主键列（用于检测重复）
        schema: 列类型定义

    """

    dataset: str
    key_columns: tuple[str, ...]
    schema: dict[str, type[pl.DataType]]
