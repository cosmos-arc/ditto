"""ColumnMapping 类定义."""

from __future__ import annotations

from dataclasses import dataclass, field

import polars as pl

from ditto_data.sources.normalization import NormalizationConfig


@dataclass(frozen=True)
class ColumnMapping:
    """
    列映射配置（扩展版）.

    Attributes:
        rename: 列重命名映射
        date_columns: 日期列及格式映射（列名 -> 格式）
        float_columns: 需要转换为 Float64 的列
        int_columns: 需要转换为 Int64 的列
        boolean_columns: 需要转换为 Boolean 的列
        computed_columns: 计算列映射（列名 -> Polars 表达式）
        output_columns: 需要保留的输出列，None 表示保留所有列
        normalization: 数据标准化配置

    """

    rename: dict[str, str]
    date_columns: dict[str, str]  # 列名 -> 格式
    float_columns: list[str]
    int_columns: tuple[str, ...] = ()
    boolean_columns: tuple[str, ...] = ()
    # 计算列：列名 -> Polars 表达式（用于动态计算，如从 ts_code 提取 ticker/exchange）
    computed_columns: dict[str, pl.Expr] = field(default_factory=lambda: {})
    # 需要保留的输出列（重命名后），None 表示保留所有列
    output_columns: tuple[str, ...] | None = None
    # 标准化配置
    normalization: NormalizationConfig | None = None
