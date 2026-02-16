"""Tushare data transformation utilities."""

from __future__ import annotations

import polars as pl
from ditto_infra.foundation import Metrics, logger

from ditto_datahub.sources.tushare.processors.column_mapping import ColumnMapping

# 重新导出所有 Mapping（保持向后兼容）
from .mappings import (
    ADJ_FACTOR_MAPPING,
    BALANCE_SHEET_MAPPING,
    CALENDAR_MAPPING,
    CASH_FLOW_MAPPING,
    CORPORATE_ACTIONS_MAPPING,
    DAILY_OHLCV_MAPPING,
    DIVIDEND_MAPPING,
    ETF_BASIC_MAPPING,
    FUND_ADJ_MAPPING,
    FUTURES_MAPPING,
    INCOME_STATEMENT_MAPPING,
    INDEX_BASIC_MAPPING,
    INDEX_COMPOSITION_MAPPING,
    MARGIN_TRADING_MAPPING,
    PLEDGE_RATIO_MAPPING,
    STOCK_BASIC_MAPPING,
    STOCK_LIMIT_MAPPING,
    VALUATION_METRICS_MAPPING,
)

__all__ = [
    "ADJ_FACTOR_MAPPING",
    "BALANCE_SHEET_MAPPING",
    "CALENDAR_MAPPING",
    "CASH_FLOW_MAPPING",
    "CORPORATE_ACTIONS_MAPPING",
    "DAILY_OHLCV_MAPPING",
    "DIVIDEND_MAPPING",
    "ETF_BASIC_MAPPING",
    "FUND_ADJ_MAPPING",
    "FUTURES_MAPPING",
    "INCOME_STATEMENT_MAPPING",
    "INDEX_BASIC_MAPPING",
    "INDEX_COMPOSITION_MAPPING",
    "MARGIN_TRADING_MAPPING",
    "PLEDGE_RATIO_MAPPING",
    "STOCK_BASIC_MAPPING",
    "STOCK_LIMIT_MAPPING",
    "VALUATION_METRICS_MAPPING",
    "ColumnMapping",
    "TushareDataTransformer",
]


class TushareDataTransformer:
    """Tushare 数据转换工具类."""

    @staticmethod
    def transform(
        df: pl.DataFrame,
        dataset_name: str,
        mapping: ColumnMapping,
    ) -> pl.DataFrame:
        """
        统一转换 Tushare 数据.

        Args:
            df: 输入的 DataFrame（来自 Tushare API）
            dataset_name: 数据集名称（用于日志）
            mapping: 列映射配置

        Returns:
            转换后的 DataFrame

        """
        # 1. 空处理：直接使用 _build_schema_from_mapping 构建 schema
        if len(df) == 0:
            logger.info(
                f"Tushare {dataset_name} empty",
                event=f"tushare_{dataset_name}_fetch_complete",
                row_count=0,
            )
            schema = TushareDataTransformer._build_schema_from_mapping(mapping)
            return pl.DataFrame(schema=schema)

        # 执行实际转换
        result = TushareDataTransformer._transform_impl(df, mapping)

        # 记录日志和指标
        logger.info(
            f"Tushare {dataset_name} fetched",
            event=f"tushare_{dataset_name}_fetch_complete",
            row_count=len(result),
        )
        Metrics.data_records.add(
            len(result),
            {"source": "tushare", "dataset": dataset_name, "status": "success"},
        )

        return result

    @staticmethod
    def _transform_impl(df: pl.DataFrame, mapping: ColumnMapping) -> pl.DataFrame:
        """
        执行实际的数据转换（内部方法）.

        Args:
            df: 输入的 DataFrame
            mapping: 列映射配置

        Returns:
            转换后的 DataFrame

        """
        # 1. 应用列重命名
        result = df.rename(mapping.rename)

        # 2. 应用类型转换
        transforms: list[pl.Expr] = []
        for col, fmt in mapping.date_columns.items():
            transforms.append(pl.col(col).str.to_date(fmt))
        for col in mapping.float_columns:
            transforms.append(pl.col(col).cast(pl.Float64))
        for col in mapping.int_columns:
            transforms.append(pl.col(col).cast(pl.Int64))
        for col in mapping.boolean_columns:
            # 将整数 0/1 转换为 Boolean 类型
            transforms.append(pl.col(col).cast(pl.Boolean))

        if transforms:
            result = result.with_columns(transforms)

        # 3. 应用计算列（computed_columns）
        if mapping.computed_columns:
            result = result.with_columns(**mapping.computed_columns)

        # 4. 选择指定的输出列
        if mapping.output_columns is not None:
            result = result.select(mapping.output_columns)

        return result

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
        transforms: list[pl.Expr] = []
        for col, fmt in mapping.date_columns.items():
            transforms.append(pl.col(col).str.to_date(fmt))
        for col in mapping.float_columns:
            transforms.append(pl.col(col).cast(pl.Float64))
        for col in mapping.int_columns:
            transforms.append(pl.col(col).cast(pl.Int64))

        if transforms:
            result = result.with_columns(transforms)

        # 应用计算列（computed_columns）
        if mapping.computed_columns:
            result = result.with_columns(**mapping.computed_columns)

        # 选择指定的输出列
        if mapping.output_columns is not None:
            result = result.select(mapping.output_columns)

        logger.info(
            f"Tushare {dataset_name} fetched",
            event=f"tushare_{dataset_name}_fetch_complete",
            row_count=len(result),
        )
        Metrics.data_records.add(
            len(result),
            {"source": "tushare", "dataset": dataset_name, "status": "success"},
        )

        return result

    @staticmethod
    def _build_column_type_map(
        mapping: ColumnMapping,
    ) -> dict[str, type[pl.DataType]]:
        """构建列名到类型的映射."""
        column_types: dict[str, type[pl.DataType]] = {}
        for col in mapping.date_columns:
            column_types[col] = pl.Date
        for col in mapping.float_columns:
            column_types[col] = pl.Float64
        for col in mapping.int_columns:
            column_types[col] = pl.Int64
        for col in mapping.boolean_columns:
            column_types[col] = pl.Boolean
        return column_types

    @staticmethod
    def _infer_computed_column_type(
        expr: pl.Expr, column_types: dict[str, type[pl.DataType]]
    ) -> type[pl.DataType]:
        """从表达式推断计算列的类型."""
        try:
            root_names = expr.meta.root_names()
            if len(root_names) == 1:
                return column_types.get(root_names[0], pl.String)
        except Exception as e:
            logger.debug("Failed to infer column type from expression", error=str(e))
        return pl.String

    @staticmethod
    def _build_schema_from_mapping(
        mapping: ColumnMapping,
    ) -> dict[str, type[pl.DataType]]:
        """
        从映射配置构建 schema.

        此方法用于空数据处理场景,当 API 返回空数据时,
        仍需返回正确 schema 的 DataFrame 以确保下游类型正确.

        Args:
            mapping: 列映射配置

        Returns:
            schema 字典,包含所有 output_columns 中指定的列及其类型

        Note:
            - 对于未在类型配置中明确指定的列(如 name),默认使用 String 类型
            - computed_columns 的类型通过 _infer_computed_column_type 推断
            - 确保 output_columns 中的所有列都在 schema 中

        """
        schema: dict[str, type[pl.DataType]] = {}
        columns_to_include = mapping.output_columns
        column_types = TushareDataTransformer._build_column_type_map(mapping)

        # 处理重命名的列
        for old_name, new_name in mapping.rename.items():
            if columns_to_include is None or new_name in columns_to_include:
                schema[new_name] = column_types.get(old_name, pl.String)

        # 处理未重命名的列
        for col, dtype in column_types.items():
            should_include = columns_to_include is None or col in columns_to_include
            if col not in mapping.rename and should_include:
                schema[col] = dtype

        # 处理计算列
        for col_name, expr in mapping.computed_columns.items():
            if columns_to_include is None or col_name in columns_to_include:
                schema[col_name] = TushareDataTransformer._infer_computed_column_type(
                    expr, column_types
                )

        # 处理在 output_columns 中但尚未添加的列(如 name,这些列没有在类型配置中)
        # 这些列默认为 String 类型
        if columns_to_include is not None:
            for col in columns_to_include:
                if col not in schema:
                    schema[col] = pl.String

        return schema
