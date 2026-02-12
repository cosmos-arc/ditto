"""
SourceSchema - 数据源输出格式定义

定义数据源输出的列结构和类型，作为 Source 层的契约。
"""

from dataclasses import dataclass, field

import polars as pl


@dataclass(frozen=True)
class SourceSchema:
    """
    数据源输出格式定义

    定义数据源输出的列结构和类型，作为 Source 层的契约。

    Attributes:
        dataset: 数据集标识
        key_columns: 主键列
        schema: 列类型定义
        pit_columns: PIT（Point-in-Time）列

    """

    dataset: str
    key_columns: tuple[str, ...]
    schema: dict[str, type[pl.DataType]]
    pit_columns: tuple[str, ...] = field(default_factory=tuple)
