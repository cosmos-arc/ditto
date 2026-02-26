"""Commodity schema tests."""

import polars as pl
from ditto_datahub.sources.schemas.commodity_schemas import COMMODITY_SOURCE_SCHEMA


class TestCommoditySourceSchema:
    """商品源数据 Schema 测试."""

    def test_schema_dataset_name(self) -> None:
        """测试 Schema 数据集名称正确."""
        assert COMMODITY_SOURCE_SCHEMA.dataset == "commodity_daily"

    def test_schema_key_columns(self) -> None:
        """测试 Schema 主键列正确."""
        assert "instrument_id" in COMMODITY_SOURCE_SCHEMA.key_columns
        assert "trade_date" in COMMODITY_SOURCE_SCHEMA.key_columns

    def test_schema_has_required_fields(self) -> None:
        """测试 Schema 包含必要字段."""
        schema = COMMODITY_SOURCE_SCHEMA.schema
        assert "instrument_id" in schema
        assert "trade_date" in schema
        assert "open" in schema
        assert "high" in schema
        assert "low" in schema
        assert "close" in schema

    def test_schema_field_types(self) -> None:
        """测试 Schema 字段类型正确."""
        schema = COMMODITY_SOURCE_SCHEMA.schema
        assert schema["instrument_id"] == pl.Int64
        assert schema["trade_date"] == pl.Date
        assert schema["open"] == pl.Float64
        assert schema["high"] == pl.Float64
        assert schema["low"] == pl.Float64
        assert schema["close"] == pl.Float64

    def test_schema_no_pit_columns(self) -> None:
        """测试商品数据不需要 PIT 列."""
        assert COMMODITY_SOURCE_SCHEMA.pit_columns == ()
