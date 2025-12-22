"""Tests for Schema definitions."""

import polars as pl
from ditto_datahub.meta.schemas import (
    ADJ_FACTOR_SCHEMA,
    ETF_DAILY_SCHEMA,
    INDEX_DAILY_SCHEMA,
    INDEX_WEIGHT_SCHEMA,
    STOCK_DAILY_SCHEMA,
    UNIVERSE_CONSTITUENT_SCHEMA,
)


class TestStockDailySchema:
    """Tests for STOCK_DAILY_SCHEMA."""

    def test_schema_is_dict(self) -> None:
        """Schema should be a dictionary."""
        assert isinstance(STOCK_DAILY_SCHEMA, dict)

    def test_schema_has_all_required_fields(self) -> None:
        """Schema should have all required fields."""
        required_fields = {
            "sid",
            "trade_date",
            "source",
            "src_code",
            "open",
            "high",
            "low",
            "close",
            "pre_close",
            "volume",
            "amount",
            "pct_change",
            "turnover",
            "is_suspended",
            "is_limit_up",
            "is_limit_down",
            "is_st",
        }
        assert set(STOCK_DAILY_SCHEMA.keys()) == required_fields

    def test_schema_types_are_polars_types(self) -> None:
        """Schema values should be Polars data types."""
        # Check that all values are Polars type classes
        valid_types = (pl.Int64, pl.Float64, pl.Date, pl.Utf8, pl.Boolean)
        for dtype in STOCK_DAILY_SCHEMA.values():
            assert dtype in valid_types

    def test_sid_is_int64(self) -> None:
        """Sid field should be Int64."""
        assert STOCK_DAILY_SCHEMA["sid"] == pl.Int64

    def test_trade_date_is_date(self) -> None:
        """trade_date field should be Date."""
        assert STOCK_DAILY_SCHEMA["trade_date"] == pl.Date

    def test_price_fields_are_float64(self) -> None:
        """Price fields should be Float64."""
        price_fields = ["open", "high", "low", "close", "pre_close"]
        for field in price_fields:
            assert STOCK_DAILY_SCHEMA[field] == pl.Float64

    def test_boolean_fields_are_boolean(self) -> None:
        """Boolean fields should be Boolean."""
        bool_fields = ["is_suspended", "is_limit_up", "is_limit_down", "is_st"]
        for field in bool_fields:
            assert STOCK_DAILY_SCHEMA[field] == pl.Boolean


class TestEtfDailySchema:
    """Tests for ETF_DAILY_SCHEMA."""

    def test_schema_is_dict(self) -> None:
        """Schema should be a dictionary."""
        assert isinstance(ETF_DAILY_SCHEMA, dict)

    def test_schema_has_all_required_fields(self) -> None:
        """Schema should have all required fields."""
        required_fields = {
            "sid",
            "trade_date",
            "source",
            "src_code",
            "open",
            "high",
            "low",
            "close",
            "pre_close",
            "volume",
            "amount",
            "pct_change",
        }
        assert set(ETF_DAILY_SCHEMA.keys()) == required_fields

    def test_schema_types_are_polars_types(self) -> None:
        """Schema values should be Polars data types."""
        valid_types = (pl.Int64, pl.Float64, pl.Date, pl.Utf8)
        for dtype in ETF_DAILY_SCHEMA.values():
            assert dtype in valid_types

    def test_sid_is_int64(self) -> None:
        """Sid field should be Int64."""
        assert ETF_DAILY_SCHEMA["sid"] == pl.Int64

    def test_trade_date_is_date(self) -> None:
        """trade_date field should be Date."""
        assert ETF_DAILY_SCHEMA["trade_date"] == pl.Date


class TestIndexDailySchema:
    """Tests for INDEX_DAILY_SCHEMA."""

    def test_schema_is_dict(self) -> None:
        """Schema should be a dictionary."""
        assert isinstance(INDEX_DAILY_SCHEMA, dict)

    def test_schema_has_all_required_fields(self) -> None:
        """Schema should have all required fields."""
        required_fields = {
            "sid",
            "trade_date",
            "source",
            "src_code",
            "open",
            "high",
            "low",
            "close",
            "pre_close",
            "change",
            "pct_change",
            "volume",
            "amount",
        }
        assert set(INDEX_DAILY_SCHEMA.keys()) == required_fields

    def test_schema_types_are_polars_types(self) -> None:
        """Schema values should be Polars data types."""
        valid_types = (pl.Int64, pl.Float64, pl.Date, pl.Utf8)
        for dtype in INDEX_DAILY_SCHEMA.values():
            assert dtype in valid_types

    def test_has_change_field(self) -> None:
        """Index schema should have change field."""
        assert "change" in INDEX_DAILY_SCHEMA
        assert INDEX_DAILY_SCHEMA["change"] == pl.Float64


class TestAdjFactorSchema:
    """Tests for ADJ_FACTOR_SCHEMA."""

    def test_schema_is_dict(self) -> None:
        """Schema should be a dictionary."""
        assert isinstance(ADJ_FACTOR_SCHEMA, dict)

    def test_schema_has_all_required_fields(self) -> None:
        """Schema should have all required fields."""
        required_fields = {
            "sid",
            "trade_date",
            "source",
            "src_code",
            "adj_factor",
        }
        assert set(ADJ_FACTOR_SCHEMA.keys()) == required_fields

    def test_adj_factor_is_float64(self) -> None:
        """adj_factor field should be Float64."""
        assert ADJ_FACTOR_SCHEMA["adj_factor"] == pl.Float64


class TestIndexWeightSchema:
    """Tests for INDEX_WEIGHT_SCHEMA."""

    def test_schema_is_dict(self) -> None:
        """Schema should be a dictionary."""
        assert isinstance(INDEX_WEIGHT_SCHEMA, dict)

    def test_schema_has_all_required_fields(self) -> None:
        """Schema should have all required fields."""
        required_fields = {
            "index_sid",
            "con_sid",
            "trade_date",
            "weight",
            "source",
            "index_code",
            "con_code",
        }
        assert set(INDEX_WEIGHT_SCHEMA.keys()) == required_fields

    def test_weight_is_float64(self) -> None:
        """Weight field should be Float64."""
        assert INDEX_WEIGHT_SCHEMA["weight"] == pl.Float64


class TestUniverseConstituentSchema:
    """Tests for UNIVERSE_CONSTITUENT_SCHEMA."""

    def test_schema_is_dict(self) -> None:
        """Schema should be a dictionary."""
        assert isinstance(UNIVERSE_CONSTITUENT_SCHEMA, dict)

    def test_schema_has_all_required_fields(self) -> None:
        """Schema should have all required fields."""
        required_fields = {
            "universe_id",
            "sid",
            "source",
            "src_code",
            "effective_from",
            "effective_to",
            "weight",
        }
        assert set(UNIVERSE_CONSTITUENT_SCHEMA.keys()) == required_fields

    def test_has_effective_dates(self) -> None:
        """Schema should have effective_from and effective_to for PIT."""
        assert "effective_from" in UNIVERSE_CONSTITUENT_SCHEMA
        assert "effective_to" in UNIVERSE_CONSTITUENT_SCHEMA
        assert UNIVERSE_CONSTITUENT_SCHEMA["effective_from"] == pl.Date
        assert UNIVERSE_CONSTITUENT_SCHEMA["effective_to"] == pl.Date
