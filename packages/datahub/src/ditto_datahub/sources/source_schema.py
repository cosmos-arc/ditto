"""
SourceSchema - 数据源输出格式定义

定义数据源输出的列结构和类型，作为 Source 层的契约。
"""

from __future__ import annotations

from dataclasses import dataclass, field

import polars as pl

# Schema 类型可以是类型类（如 pl.Int64）或实例（如 pl.Datetime("ms")）
SchemaType = dict[str, type[pl.DataType] | pl.DataType]


@dataclass(frozen=True)
class SourceSchema:
    """
    数据源输出格式定义

    定义数据源输出的列结构和类型，作为 Source 层的契约。

    Attributes:
        dataset: 数据集标识
        key_columns: 主键列
        schema: 列类型定义（支持类型类或实例）
        pit_columns: PIT（Point-in-Time）列

    """

    dataset: str
    key_columns: tuple[str, ...]
    schema: SchemaType
    pit_columns: tuple[str, ...] = field(default_factory=tuple)
