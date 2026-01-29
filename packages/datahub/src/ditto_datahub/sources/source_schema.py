"""
SourceSchema - 数据源输出格式标准协议

定义数据源必须遵循的输出规范，作为 Source 和 Store 之间的契约。
"""

from dataclasses import dataclass, field

import polars as pl

from ditto_datahub.errors import SchemaValidationError


@dataclass(frozen=True)
class SourceSchema:
    """
    数据源输出格式标准协议

    定义数据源必须遵循的输出规范，作为 Source 和 Store 之间的契约。

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

    def validate(self, df: pl.DataFrame) -> None:
        """
        验证 DataFrame 是否符合 Schema

        Args:
            df: 待验证的 DataFrame

        Raises:
            SchemaValidationError: 验证失败时抛出

        """
        # 1. 检查列完整性
        missing = set(self.schema.keys()) - set(df.columns)
        if missing:
            raise SchemaValidationError(f"Missing columns: {missing}")

        # 2. 检查类型兼容性
        for col, expected_type in self.schema.items():
            if col in df.columns:
                actual_type = df.schema[col]
                if not self._is_type_compatible(actual_type, expected_type):
                    raise SchemaValidationError(
                        f"Column '{col}': expected {expected_type}, got {actual_type}"
                    )

        # 3. 检查主键唯一性
        if self.key_columns and len(df) > 0:
            key_count = df.select(pl.len()).item()
            unique_count = df.unique(self.key_columns).select(pl.len()).item()
            if key_count != unique_count:
                raise SchemaValidationError(f"Duplicate keys in {self.key_columns}")

    def _is_type_compatible(
        self,
        actual: pl.DataType,
        expected: type[pl.DataType],
    ) -> bool:
        """
        检查类型是否兼容

        Args:
            actual: 实际的 Polars 数据类型
            expected: 期望的 Polars 数据类型

        Returns:
            类型兼容返回 True，否则返回 False

        """
        # 完全匹配
        if isinstance(actual, expected):
            return True

        # 数值类型兼容性：Int 可以向上兼容到 Float
        numeric_compatibility = {
            pl.Int8: [pl.Int16, pl.Int32, pl.Int64, pl.Float32, pl.Float64],
            pl.Int16: [pl.Int32, pl.Int64, pl.Float32, pl.Float64],
            pl.Int32: [pl.Int64, pl.Float32, pl.Float64],
            pl.Int64: [pl.Float32, pl.Float64],
            pl.Float32: [pl.Float64],
        }

        # 检查数值类型兼容性
        for base_type, compatible_types in numeric_compatibility.items():
            if (
                isinstance(actual, base_type)
                and any(isinstance(actual, t) for t in compatible_types)
                and expected in compatible_types
            ):
                return True

        # 临时类型（Null）在验证时可以忽略
        return bool(isinstance(actual, pl.Null))
