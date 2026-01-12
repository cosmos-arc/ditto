"""Tushare data transformation utilities."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import polars as pl
from ditto_foundation import M, logger

if TYPE_CHECKING:
    from polars.type_aliases import PolarsDataType


__all__ = ["DAILY_OHLCV_MAPPING", "ColumnMapping", "TushareDataTransformer"]


@dataclass(frozen=True)
class ColumnMapping:
    """列映射配置."""

    rename: dict[str, str]
    date_columns: dict[str, str]  # 列名 -> 格式
    float_columns: list[str]
    int_columns: tuple[str, ...] = ()
    boolean_columns: tuple[str, ...] = ()
    # 计算列：列名 -> Polars 表达式（用于动态计算，如从 ts_code 提取 symbol/exchange）
    computed_columns: dict[str, pl.Expr] = field(default_factory=dict)
    # 需要保留的输出列（重命名后），None 表示保留所有列
    output_columns: tuple[str, ...] | None = None


# OHLCV 数据的通用配置
DAILY_OHLCV_MAPPING = ColumnMapping(
    rename={"ts_code": "src_code", "vol": "volume", "pct_chg": "pct_change"},
    date_columns={"trade_date": "%Y%m%d"},
    float_columns=[
        "open",
        "high",
        "low",
        "close",
        "pre_close",
        "volume",
        "amount",
        "pct_change",
    ],
    output_columns=(
        "src_code",
        "trade_date",
        "open",
        "high",
        "low",
        "close",
        "pre_close",
        "volume",
        "amount",
        "pct_change",
    ),
)


class TushareDataTransformer:
    """Tushare 数据转换工具类."""

    @staticmethod
    def transform_daily_ohlcv(
        df: pl.DataFrame,
        dataset_name: str,
        mapping: ColumnMapping = DAILY_OHLCV_MAPPING,
    ) -> pl.DataFrame:
        """
        统一转换 daily OHLCV 数据.

        Args:
            df: 输入的 DataFrame（来自 Tushare API）
            dataset_name: 数据集名称（用于日志）
            mapping: 列映射配置

        Returns:
            转换后的 DataFrame

        """
        if len(df) == 0:
            logger.info(
                f"Tushare {dataset_name} empty",
                event=f"tushare_{dataset_name}_fetch_complete",
                row_count=0,
            )
            schema = TushareDataTransformer._build_schema_from_mapping(mapping)
            return pl.DataFrame(schema=schema)

        # 应用列映射
        result = df.rename(mapping.rename)

        # 应用类型转换
        transforms = []
        for col, fmt in mapping.date_columns.items():
            transforms.append(pl.col(col).str.to_date(fmt))
        for col in mapping.float_columns:
            transforms.append(pl.col(col).cast(pl.Float64))
        for col in mapping.int_columns:
            transforms.append(pl.col(col).cast(pl.Int64))

        if transforms:
            result = result.with_columns(transforms)

        # 选择指定的输出列
        if mapping.output_columns is not None:
            result = result.select(mapping.output_columns)

        logger.info(
            f"Tushare {dataset_name} fetched",
            event=f"tushare_{dataset_name}_fetch_complete",
            row_count=len(result),
        )
        M.data_records.add(
            len(result),
            {"source": "tushare", "dataset": dataset_name, "status": "success"},
        )

        return result

    @staticmethod
    def _build_schema_from_mapping(mapping: ColumnMapping) -> dict[str, PolarsDataType]:
        """
        从映射配置构建 schema.

        Args:
            mapping: 列映射配置

        Returns:
            schema 字典

        """
        schema: dict[str, PolarsDataType] = {}

        # 如果指定了 output_columns，只构建这些列的 schema
        columns_to_include = mapping.output_columns

        # 构建列类型映射
        column_types: dict[str, PolarsDataType] = {}
        for col in mapping.date_columns:
            column_types[col] = pl.Date
        for col in mapping.float_columns:
            column_types[col] = pl.Float64
        for col in mapping.int_columns:
            column_types[col] = pl.Int64

        # 处理所有列（重命名后的）
        for old_name, new_name in mapping.rename.items():
            final_name = new_name
            final_type = column_types.get(old_name, pl.String)

            if columns_to_include is None or final_name in columns_to_include:
                schema[final_name] = final_type

        # 处理没有重命名的列
        for col, dtype in column_types.items():
            if col not in mapping.rename and (
                columns_to_include is None or col in columns_to_include
            ):
                schema[col] = dtype

        return schema
