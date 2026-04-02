"""FX schema tests."""

import polars as pl
from ditto_data.sources.schemas.fx_schemas import FX_SOURCE_SCHEMA


class TestFxSourceSchema:
    """汇率源数据 Schema 测试."""

    def test_schema_dataset_name(self) -> None:
        """测试 Schema 数据集名称正确."""
        assert FX_SOURCE_SCHEMA.dataset == "fx_daily"

    def test_schema_key_columns(self) -> None:
        """测试 Schema 主键列正确."""
        assert "instrument_id" in FX_SOURCE_SCHEMA.key_columns
        assert "trade_date" in FX_SOURCE_SCHEMA.key_columns

    def test_schema_has_required_fields(self) -> None:
        """测试 Schema 包含必要字段."""
        schema = FX_SOURCE_SCHEMA.schema
        assert "instrument_id" in schema
        assert "trade_date" in schema
        assert "open" in schema
        assert "high" in schema
        assert "low" in schema
        assert "close" in schema

    def test_schema_field_types(self) -> None:
        """测试 Schema 字段类型正确."""
        schema = FX_SOURCE_SCHEMA.schema
        assert schema["instrument_id"] == pl.Int64
        assert schema["trade_date"] == pl.Date
        assert schema["open"] == pl.Float64
        assert schema["high"] == pl.Float64
        assert schema["low"] == pl.Float64
        assert schema["close"] == pl.Float64

    def test_schema_has_trade_date_utc(self) -> None:
        """测试 FX Schema 包含 trade_date_utc 字段（UTC 午夜时间戳）."""
        schema = FX_SOURCE_SCHEMA.schema
        assert "trade_date_utc" in schema
        assert schema["trade_date_utc"] == pl.Datetime("ms")

    def test_schema_no_pit_columns(self) -> None:
        """测试汇率数据不需要 PIT 列."""
        assert FX_SOURCE_SCHEMA.pit_columns == ()
