"""Market 模型单元测试."""

from datetime import date, time

import polars as pl
from ditto_data.models.market import (
    BAR_ENRICHED_SCHEMA,
    BAR_SCHEMA,
    QUOTE_SCHEMA,
)


class TestBarSchema:
    """BAR_SCHEMA 测试."""

    def test_bar_schema_structure(self) -> None:
        """测试 BAR_SCHEMA 包含所有必需字段."""
        expected_keys = {
            "instrument_id",
            "trade_date",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "amount",
        }
        assert set(BAR_SCHEMA.keys()) == expected_keys

    def test_bar_schema_types(self) -> None:
        """测试 BAR_SCHEMA 字段类型正确."""
        assert BAR_SCHEMA["instrument_id"] == pl.Int64
        assert BAR_SCHEMA["trade_date"] == pl.Date
        assert BAR_SCHEMA["open"] == pl.Float64
        assert BAR_SCHEMA["high"] == pl.Float64
        assert BAR_SCHEMA["low"] == pl.Float64
        assert BAR_SCHEMA["close"] == pl.Float64
        assert BAR_SCHEMA["volume"] == pl.Float64
        assert BAR_SCHEMA["amount"] == pl.Float64

    def test_bar_enriched_schema_includes_base(self) -> None:
        """测试 BAR_ENRICHED_SCHEMA 包含基础字段."""
        for key in BAR_SCHEMA:
            assert key in BAR_ENRICHED_SCHEMA

    def test_bar_enriched_schema_has_extra_fields(self) -> None:
        """测试 BAR_ENRICHED_SCHEMA 包含额外字段."""
        assert "pct_change" in BAR_ENRICHED_SCHEMA
        assert "turnover" in BAR_ENRICHED_SCHEMA
        assert BAR_ENRICHED_SCHEMA["pct_change"] == pl.Float64
        assert BAR_ENRICHED_SCHEMA["turnover"] == pl.Float64

    def test_bar_enriched_schema_field_count(self) -> None:
        """测试 BAR_ENRICHED_SCHEMA 字段数量."""
        # 基础 8 个 + pct_change + turnover = 10 个
        assert len(BAR_ENRICHED_SCHEMA) == len(BAR_SCHEMA) + 2


class TestQuoteSchema:
    """QUOTE_SCHEMA 测试."""

    def test_quote_schema_structure(self) -> None:
        """测试 QUOTE_SCHEMA 包含所有必需字段."""
        expected_keys = {
            "instrument_id",
            "trade_date",
            "trade_time",
            "price",
            "volume",
            "bid1",
            "ask1",
            "bid1_volume",
            "ask1_volume",
        }
        assert set(QUOTE_SCHEMA.keys()) == expected_keys

    def test_quote_schema_types(self) -> None:
        """测试 QUOTE_SCHEMA 字段类型正确."""
        assert QUOTE_SCHEMA["instrument_id"] == pl.Int64
        assert QUOTE_SCHEMA["trade_date"] == pl.Date
        assert QUOTE_SCHEMA["trade_time"] == pl.Time
        assert QUOTE_SCHEMA["price"] == pl.Float64
        assert QUOTE_SCHEMA["volume"] == pl.Float64
        assert QUOTE_SCHEMA["bid1"] == pl.Float64
        assert QUOTE_SCHEMA["ask1"] == pl.Float64
        assert QUOTE_SCHEMA["bid1_volume"] == pl.Float64
        assert QUOTE_SCHEMA["ask1_volume"] == pl.Float64


class TestSchemaValidation:
    """Schema 验证测试."""

    def test_valid_bar_dataframe(self) -> None:
        """测试符合 BAR_SCHEMA 的 DataFrame."""
        df = pl.DataFrame(
            {
                "instrument_id": [1, 2, 3],
                "trade_date": [date(2024, 1, 1), date(2024, 1, 2), date(2024, 1, 3)],
                "open": [10.0, 11.0, 12.0],
                "high": [10.5, 11.5, 12.5],
                "low": [9.5, 10.5, 11.5],
                "close": [10.0, 11.0, 12.0],
                "volume": [1000.0, 2000.0, 3000.0],
                "amount": [10000.0, 22000.0, 36000.0],
            },
            schema=BAR_SCHEMA,
        )
        assert df.shape == (3, 8)

    def test_valid_quote_dataframe(self) -> None:
        """测试符合 QUOTE_SCHEMA 的 DataFrame."""
        df = pl.DataFrame(
            {
                "instrument_id": [1, 2],
                "trade_date": [date(2024, 1, 1), date(2024, 1, 1)],
                "trade_time": [time(9, 30, 0), time(9, 30, 1)],
                "price": [10.0, 11.0],
                "volume": [1000.0, 2000.0],
                "bid1": [9.5, 10.5],
                "ask1": [10.5, 11.5],
                "bid1_volume": [500.0, 1000.0],
                "ask1_volume": [500.0, 1000.0],
            },
            schema=QUOTE_SCHEMA,
        )
        assert df.shape == (2, 9)
