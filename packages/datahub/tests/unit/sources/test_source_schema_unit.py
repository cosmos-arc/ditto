"""SourceSchema 单元测试

测试 SourceSchema 的验证功能。
"""

import polars as pl
import pytest
from ditto_datahub.errors import SchemaValidationError
from ditto_datahub.sources.source_schema import SourceSchema


class TestSourceSchemaValidation:
    """测试 SourceSchema.validate() 方法"""

    def test_validate_valid_dataframe(self) -> None:
        """测试验证符合 Schema 的 DataFrame"""
        schema = SourceSchema(
            dataset="test_dataset",
            key_columns=("instrument_id",),
            schema={
                "instrument_id": pl.String,
                "name": pl.String,
                "value": pl.Float64,
            },
        )

        df = pl.DataFrame(
            {
                "instrument_id": ["001", "002"],
                "name": ["测试1", "测试2"],
                "value": [1.0, 2.0],
            }
        )

        # 不应该抛出异常
        schema.validate(df)

    def test_validate_missing_columns(self) -> None:
        """测试缺失必需列时抛出异常"""
        schema = SourceSchema(
            dataset="test_dataset",
            key_columns=("instrument_id",),
            schema={
                "instrument_id": pl.String,
                "name": pl.String,
                "value": pl.Float64,
            },
        )

        # 缺少 name 列
        df = pl.DataFrame(
            {
                "instrument_id": ["001", "002"],
                "value": [1.0, 2.0],
            }
        )

        with pytest.raises(SchemaValidationError) as exc_info:
            schema.validate(df)

        assert "Missing columns" in str(exc_info.value)
        assert "name" in str(exc_info.value)

    def test_validate_type_mismatch(self) -> None:
        """测试类型不兼容时抛出异常（String vs Float64）"""
        schema = SourceSchema(
            dataset="test_dataset",
            key_columns=("instrument_id",),
            schema={
                "instrument_id": pl.String,
                "value": pl.Float64,
            },
        )

        # value 是 String，与 Float64 完全不兼容
        df = pl.DataFrame(
            {
                "instrument_id": ["001", "002"],
                "value": ["1.0", "2.0"],  # String
            }
        )

        with pytest.raises(SchemaValidationError) as exc_info:
            schema.validate(df)

        assert "value" in str(exc_info.value)
        assert "expected" in str(exc_info.value).lower()

    def test_validate_duplicate_keys(self) -> None:
        """测试主键重复时抛出异常"""
        schema = SourceSchema(
            dataset="test_dataset",
            key_columns=("instrument_id",),
            schema={
                "instrument_id": pl.String,
                "value": pl.Float64,
            },
        )

        # instrument_id 有重复
        df = pl.DataFrame(
            {
                "instrument_id": ["001", "001"],
                "value": [1.0, 2.0],
            }
        )

        with pytest.raises(SchemaValidationError) as exc_info:
            schema.validate(df)

        assert "Duplicate keys" in str(exc_info.value)

    def test_validate_composite_key_uniqueness(self) -> None:
        """测试复合主键的唯一性验证"""
        schema = SourceSchema(
            dataset="test_dataset",
            key_columns=("instrument_id", "trade_date"),
            schema={
                "instrument_id": pl.String,
                "trade_date": pl.Date,
                "value": pl.Float64,
            },
        )

        # 复合主键有重复
        df = pl.DataFrame(
            {
                "instrument_id": ["001", "001"],
                "trade_date": ["2024-01-01", "2024-01-01"],
                "value": [1.0, 2.0],
            }
        ).with_columns(pl.col("trade_date").str.to_date())

        with pytest.raises(SchemaValidationError) as exc_info:
            schema.validate(df)

        assert "Duplicate keys" in str(exc_info.value)

    def test_validate_with_pit_columns(self) -> None:
        """测试带 PIT 列的 Schema 验证"""
        schema = SourceSchema(
            dataset="test_dataset",
            key_columns=("instrument_id", "effective_from"),
            schema={
                "instrument_id": pl.String,
                "effective_from": pl.Date,
                "effective_to": pl.Date,
                "value": pl.Float64,
            },
            pit_columns=("effective_from", "effective_to"),
        )

        df = pl.DataFrame(
            {
                "instrument_id": ["001", "002"],
                "effective_from": ["2024-01-01", "2024-01-01"],
                "effective_to": ["2024-02-01", None],
                "value": [1.0, 2.0],
            }
        ).with_columns(
            pl.col("effective_from").str.to_date(),
            pl.col("effective_to").str.to_date(),
        )

        # 不应该抛出异常
        schema.validate(df)

    def test_validate_empty_dataframe(self) -> None:
        """测试空 DataFrame 的验证"""
        schema = SourceSchema(
            dataset="test_dataset",
            key_columns=("instrument_id",),
            schema={
                "instrument_id": pl.String,
                "value": pl.Float64,
            },
        )

        # 创建符合 schema 的空 DataFrame
        df = pl.DataFrame(
            schema={
                "instrument_id": pl.String,
                "value": pl.Float64,
            }
        )

        # 空数据框不应该抛出异常
        schema.validate(df)

    def test_validate_type_compatible_int_to_float_no_cast(self) -> None:
        """测试 Int64 列可以直接兼容 Float64 schema（无需手动 cast）"""
        schema = SourceSchema(
            dataset="test_dataset",
            key_columns=("instrument_id",),
            schema={
                "instrument_id": pl.String,
                "value": pl.Float64,
            },
        )

        # Int64 列应该自动兼容 Float64 schema
        df = pl.DataFrame(
            {
                "instrument_id": ["001", "002"],
                "value": [1, 2],  # Int64 (不 cast)
            }
        )

        # 不应该抛出异常 - numeric widening should work
        schema.validate(df)

    def test_validate_type_compatible_int32_to_float64(self) -> None:
        """测试 Int32 可以兼容 Float64"""
        schema = SourceSchema(
            dataset="test_dataset",
            key_columns=("id",),
            schema={
                "id": pl.String,
                "value": pl.Float64,
            },
        )

        # Int32 应该可以向上兼容到 Float64
        df = pl.DataFrame(
            {
                "id": ["001", "002"],
                "value": pl.Series("value", [1, 2], dtype=pl.Int32),  # Int32
            }
        )

        # 不应该抛出异常
        schema.validate(df)

    def test_validate_type_incompatible_float_to_int(self) -> None:
        """测试 Float64 不能向下兼容到 Int64（方向错误）"""
        schema = SourceSchema(
            dataset="test_dataset",
            key_columns=("id",),
            schema={
                "id": pl.String,
                "value": pl.Int64,  # 期望 Int64
            },
        )

        # Float64 不应该兼容 Int64（方向错误，会丢失精度）
        df = pl.DataFrame(
            {
                "id": ["001", "002"],
                "value": [1.5, 2.5],  # Float64
            }
        )

        # 应该抛出异常
        with pytest.raises(SchemaValidationError) as exc_info:
            schema.validate(df)

        assert "value" in str(exc_info.value)
