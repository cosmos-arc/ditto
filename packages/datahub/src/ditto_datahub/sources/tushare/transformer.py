"""Tushare data transformation utilities."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import polars as pl
from ditto_foundation import M, logger

if TYPE_CHECKING:
    from polars.type_aliases import PolarsDataType


__all__ = [
    "ADJ_FACTOR_MAPPING",
    "CALENDAR_MAPPING",
    "DAILY_OHLCV_MAPPING",
    "ETF_BASIC_MAPPING",
    "FUND_ADJ_MAPPING",
    "STOCK_BASIC_MAPPING",
    "STOCK_LIMIT_MAPPING",
    "ColumnMapping",
    "TushareDataTransformer",
]


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

# 交易日历配置
CALENDAR_MAPPING = ColumnMapping(
    rename={"cal_date": "trade_date"},
    date_columns={"trade_date": "%Y%m%d"},
    float_columns=[],
    boolean_columns=("is_open",),
    output_columns=("trade_date", "is_open"),
)

# 复权因子配置（股票）
# knowledge_date = trade_date（数据即日可用，直接复制已转换的 Date 列）
ADJ_FACTOR_MAPPING = ColumnMapping(
    rename={"ts_code": "src_code"},
    date_columns={"trade_date": "%Y%m%d"},
    float_columns=["adj_factor"],
    computed_columns={"knowledge_date": pl.col("trade_date")},
    output_columns=("src_code", "trade_date", "knowledge_date", "adj_factor"),
)

# 复权因子配置（ETF/基金）- 与股票复权因子结构相同
FUND_ADJ_MAPPING = ColumnMapping(
    rename={"ts_code": "src_code"},
    date_columns={"trade_date": "%Y%m%d"},
    float_columns=["adj_factor"],
    computed_columns={"knowledge_date": pl.col("trade_date")},
    output_columns=("src_code", "trade_date", "knowledge_date", "adj_factor"),
)

# ETF 基本信息配置
ETF_BASIC_MAPPING = ColumnMapping(
    rename={"ts_code": "src_code"},
    date_columns={"list_date": "%Y%m%d"},
    float_columns=[],
    computed_columns={
        "symbol": pl.col("src_code").str.split(".").list.get(0),
        "exchange": pl.col("src_code")
        .str.split(".")
        .list.get(1)
        .replace({"SH": "SSE", "SZ": "SZSE"}),
    },
    output_columns=("src_code", "symbol", "name", "exchange", "list_date"),
)

# 股票基本信息配置
STOCK_BASIC_MAPPING = ColumnMapping(
    rename={"ts_code": "src_code"},
    date_columns={"list_date": "%Y%m%d"},
    float_columns=[],
    output_columns=("src_code", "symbol", "name", "exchange", "list_date"),
)

# 涨跌停价格配置
STOCK_LIMIT_MAPPING = ColumnMapping(
    rename={"ts_code": "src_code"},
    date_columns={"trade_date": "%Y%m%d"},
    float_columns=["up_limit", "down_limit"],
    output_columns=("src_code", "trade_date", "up_limit", "down_limit"),
)


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
        # 1. 空处理：使用 dummy 数据执行转换以获取正确的 schema
        if len(df) == 0:
            logger.info(
                f"Tushare {dataset_name} empty",
                event=f"tushare_{dataset_name}_fetch_complete",
                row_count=0,
            )
            # 创建单行 dummy 数据，使用有效的格式
            dummy_data: dict[str, list[str | int]] = {}
            for col in df.columns:
                # 获取重命名后的列名
                renamed_col = mapping.rename.get(col, col)
                # 根据列类型生成有效的 dummy 值
                if renamed_col in mapping.date_columns:
                    dummy_data[col] = ["20240101"]
                elif renamed_col in mapping.float_columns:
                    dummy_data[col] = ["0.0"]
                elif renamed_col in mapping.int_columns:
                    dummy_data[col] = ["0"]
                elif renamed_col in mapping.boolean_columns:
                    dummy_data[col] = [0]
                else:
                    dummy_data[col] = ["dummy"]
            dummy_df = pl.DataFrame(dummy_data)
            # 执行转换获取正确 schema
            transformed = TushareDataTransformer._transform_impl(dummy_df, mapping)
            return pl.DataFrame(schema=transformed.schema)

        # 执行实际转换
        result = TushareDataTransformer._transform_impl(df, mapping)

        # 记录日志和指标
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
        transforms = []
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
        for col in mapping.boolean_columns:
            column_types[col] = pl.Boolean

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

        # 处理 computed_columns（计算列）
        # 注意：由于无法从 Polars 表达式推断确切类型，我们使用 String 作为默认类型
        # 对于 Date 类型的计算列，需要在实际转换时才能确定正确类型
        for col_name in mapping.computed_columns:
            if columns_to_include is None or col_name in columns_to_include:
                # 默认使用 String 类型，实际类型会在转换时确定
                # 如果表达式明确是 Date 类型，会在运行时正确转换
                schema[col_name] = pl.String

        return schema
