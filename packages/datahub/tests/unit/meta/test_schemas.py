"""Tests for Schema definitions."""

import polars as pl
from ditto_datahub.meta.schemas import (
    ADJ_FACTOR_SCHEMA,
    ETF_DAILY_SCHEMA,
    INDEX_DAILY_SCHEMA,
    INDEX_WEIGHT_SCHEMA,
    STOCK_DAILY_SCHEMA,
    STOCK_STATUS_SCHEMA,  # B.3: Stock status schema
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
            "up_limit",  # B.3: limit up price
            "down_limit",  # B.3: limit down price
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
            "knowledge_date",  # B.1: PIT safety for adjustment factors
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


class TestStockDailySchemaLimitPrices:
    """Tests for STOCK_DAILY_SCHEMA limit price fields (B.3)."""

    def test_has_up_limit_field(self) -> None:
        """Schema should have up_limit field for limit up price."""
        assert "up_limit" in STOCK_DAILY_SCHEMA
        assert STOCK_DAILY_SCHEMA["up_limit"] == pl.Float64

    def test_has_down_limit_field(self) -> None:
        """Schema should have down_limit field for limit down price."""
        assert "down_limit" in STOCK_DAILY_SCHEMA
        assert STOCK_DAILY_SCHEMA["down_limit"] == pl.Float64

    def test_limit_price_fields_are_float64(self) -> None:
        """Limit price fields should be Float64."""
        limit_fields = ["up_limit", "down_limit"]
        for field in limit_fields:
            assert STOCK_DAILY_SCHEMA[field] == pl.Float64


class TestStockStatusSchema:
    """Tests for STOCK_STATUS_SCHEMA (B.3)."""

    def test_schema_is_dict(self) -> None:
        """Schema should be a dictionary."""
        assert isinstance(STOCK_STATUS_SCHEMA, dict)

    def test_schema_has_all_required_fields(self) -> None:
        """Schema should have all required fields."""
        required_fields = {
            "sid",
            "trade_date",
            "is_suspended",
            "suspend_timing",
            "is_st",
            "st_type",
            "list_status",
            "source",
            "src_code",
        }
        assert set(STOCK_STATUS_SCHEMA.keys()) == required_fields

    def test_schema_types_are_polars_types(self) -> None:
        """Schema values should be Polars data types."""
        valid_types = (pl.Int64, pl.Date, pl.Utf8, pl.Boolean)
        for dtype in STOCK_STATUS_SCHEMA.values():
            assert dtype in valid_types

    def test_sid_is_int64(self) -> None:
        """Sid field should be Int64."""
        assert STOCK_STATUS_SCHEMA["sid"] == pl.Int64

    def test_trade_date_is_date(self) -> None:
        """trade_date field should be Date."""
        assert STOCK_STATUS_SCHEMA["trade_date"] == pl.Date

    def test_boolean_fields(self) -> None:
        """Boolean status fields should be Boolean."""
        assert STOCK_STATUS_SCHEMA["is_suspended"] == pl.Boolean
        assert STOCK_STATUS_SCHEMA["is_st"] == pl.Boolean

    def test_string_fields(self) -> None:
        """String status fields should be Utf8."""
        assert STOCK_STATUS_SCHEMA["suspend_timing"] == pl.Utf8
        assert STOCK_STATUS_SCHEMA["st_type"] == pl.Utf8
        assert STOCK_STATUS_SCHEMA["list_status"] == pl.Utf8
        assert STOCK_STATUS_SCHEMA["source"] == pl.Utf8
        assert STOCK_STATUS_SCHEMA["src_code"] == pl.Utf8
