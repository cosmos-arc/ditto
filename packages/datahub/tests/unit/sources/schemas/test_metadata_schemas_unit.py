"""Tests for Metadata SourceSchema definitions."""

from datetime import date

import polars as pl
from ditto_datahub.sources.schemas.metadata_schemas import (
    INDEX_MEMBER_SOURCE_SCHEMA,
    INDUSTRY_SOURCE_SCHEMA,
    INSTRUMENT_SOURCE_SCHEMA,
)
from ditto_datahub.sources.source_schema import SourceSchema


class TestInstrumentSourceSchema:
    """Tests for INSTRUMENT_SOURCE_SCHEMA."""

    def test_schema_is_source_schema_instance(self) -> None:
        """Schema should be a SourceSchema instance."""
        assert isinstance(INSTRUMENT_SOURCE_SCHEMA, SourceSchema)

    def test_dataset_name(self) -> None:
        """Dataset name should be 'instrument'."""
        assert INSTRUMENT_SOURCE_SCHEMA.dataset == "instrument"

    def test_key_columns(self) -> None:
        """Key columns should be ('instrument_id',)."""
        assert INSTRUMENT_SOURCE_SCHEMA.key_columns == ("instrument_id",)

    def test_schema_has_all_required_fields(self) -> None:
        """Schema should have all required fields."""
        required_fields = {
            "instrument_id",
            "source_ticker",
            "ticker",
            "name",
            "exchange",
            "list_date",
            "delist_date",
            "instrument_type",
        }
        assert set(INSTRUMENT_SOURCE_SCHEMA.schema.keys()) == required_fields

    def test_schema_types_are_polars_types(self) -> None:
        """Schema values should be Polars data types."""
        valid_types = (pl.String, pl.Date)
        for dtype in INSTRUMENT_SOURCE_SCHEMA.schema.values():
            assert dtype in valid_types

    def test_instrument_id_is_string(self) -> None:
        """instrument_id field should be String."""
        assert INSTRUMENT_SOURCE_SCHEMA.schema["instrument_id"] == pl.String

    def test_source_ticker_is_string(self) -> None:
        """source_ticker field should be String."""
        assert INSTRUMENT_SOURCE_SCHEMA.schema["source_ticker"] == pl.String

    def test_ticker_is_string(self) -> None:
        """Ticker field should be String."""
        assert INSTRUMENT_SOURCE_SCHEMA.schema["ticker"] == pl.String

    def test_name_is_string(self) -> None:
        """Name field should be String."""
        assert INSTRUMENT_SOURCE_SCHEMA.schema["name"] == pl.String

    def test_exchange_is_string(self) -> None:
        """Exchange field should be String (Exchange enum value)."""
        assert INSTRUMENT_SOURCE_SCHEMA.schema["exchange"] == pl.String

    def test_list_date_is_date(self) -> None:
        """list_date field should be Date."""
        assert INSTRUMENT_SOURCE_SCHEMA.schema["list_date"] == pl.Date

    def test_delist_date_is_date(self) -> None:
        """delist_date field should be Date."""
        assert INSTRUMENT_SOURCE_SCHEMA.schema["delist_date"] == pl.Date

    def test_instrument_type_is_string(self) -> None:
        """instrument_type field should be String (InstrumentType enum value)."""
        assert INSTRUMENT_SOURCE_SCHEMA.schema["instrument_type"] == pl.String

    def test_no_pit_columns(self) -> None:
        """Schema should not have PIT columns."""
        assert INSTRUMENT_SOURCE_SCHEMA.pit_columns == ()

    def test_validate_valid_dataframe(self) -> None:
        """Should validate a valid DataFrame."""
        df = pl.DataFrame(
            {
                "instrument_id": ["inst_001"],
                "source_ticker": ["600000.SH"],
                "ticker": ["600000"],
                "name": ["Test Stock"],
                "exchange": ["SSE"],
                "list_date": [date(2020, 1, 1)],
                "delist_date": [None],
                "instrument_type": ["stock"],
            }
        )
        # Should not raise
        INSTRUMENT_SOURCE_SCHEMA.validate(df)


class TestIndustrySourceSchema:
    """Tests for INDUSTRY_SOURCE_SCHEMA."""

    def test_schema_is_source_schema_instance(self) -> None:
        """Schema should be a SourceSchema instance."""
        assert isinstance(INDUSTRY_SOURCE_SCHEMA, SourceSchema)

    def test_dataset_name(self) -> None:
        """Dataset name should be 'industry'."""
        assert INDUSTRY_SOURCE_SCHEMA.dataset == "industry"

    def test_key_columns(self) -> None:
        """Key columns should be ('instrument_id', 'industry_date')."""
        assert INDUSTRY_SOURCE_SCHEMA.key_columns == ("instrument_id", "industry_date")

    def test_schema_has_all_required_fields(self) -> None:
        """Schema should have all required fields."""
        required_fields = {
            "instrument_id",
            "industry_name",
            "industry_level",
            "industry_date",
            "knowledge_date",
        }
        assert set(INDUSTRY_SOURCE_SCHEMA.schema.keys()) == required_fields

    def test_schema_types_are_polars_types(self) -> None:
        """Schema values should be Polars data types."""
        valid_types = (pl.String, pl.Int32, pl.Date)
        for dtype in INDUSTRY_SOURCE_SCHEMA.schema.values():
            assert dtype in valid_types

    def test_instrument_id_is_string(self) -> None:
        """instrument_id field should be String."""
        assert INDUSTRY_SOURCE_SCHEMA.schema["instrument_id"] == pl.String

    def test_industry_name_is_string(self) -> None:
        """industry_name field should be String."""
        assert INDUSTRY_SOURCE_SCHEMA.schema["industry_name"] == pl.String

    def test_industry_level_is_int32(self) -> None:
        """industry_level field should be Int32."""
        assert INDUSTRY_SOURCE_SCHEMA.schema["industry_level"] == pl.Int32

    def test_industry_date_is_date(self) -> None:
        """industry_date field should be Date."""
        assert INDUSTRY_SOURCE_SCHEMA.schema["industry_date"] == pl.Date

    def test_knowledge_date_is_date(self) -> None:
        """knowledge_date field should be Date."""
        assert INDUSTRY_SOURCE_SCHEMA.schema["knowledge_date"] == pl.Date

    def test_no_pit_columns(self) -> None:
        """Schema should not have PIT columns."""
        assert INDUSTRY_SOURCE_SCHEMA.pit_columns == ()


class TestIndexMemberSourceSchema:
    """Tests for INDEX_MEMBER_SOURCE_SCHEMA."""

    def test_schema_is_source_schema_instance(self) -> None:
        """Schema should be a SourceSchema instance."""
        assert isinstance(INDEX_MEMBER_SOURCE_SCHEMA, SourceSchema)

    def test_dataset_name(self) -> None:
        """Dataset name should be 'index_member'."""
        assert INDEX_MEMBER_SOURCE_SCHEMA.dataset == "index_member"

    def test_key_columns(self) -> None:
        """Key columns should include PIT columns."""
        assert INDEX_MEMBER_SOURCE_SCHEMA.key_columns == (
            "index_id",
            "instrument_id",
            "effective_from",
        )

    def test_schema_has_all_required_fields(self) -> None:
        """Schema should have all required fields."""
        required_fields = {
            "index_id",
            "instrument_id",
            "weight",
            "effective_from",
            "effective_to",
        }
        assert set(INDEX_MEMBER_SOURCE_SCHEMA.schema.keys()) == required_fields

    def test_schema_types_are_polars_types(self) -> None:
        """Schema values should be Polars data types."""
        valid_types = (pl.String, pl.Float64, pl.Date)
        for dtype in INDEX_MEMBER_SOURCE_SCHEMA.schema.values():
            assert dtype in valid_types

    def test_index_id_is_string(self) -> None:
        """index_id field should be String."""
        assert INDEX_MEMBER_SOURCE_SCHEMA.schema["index_id"] == pl.String

    def test_instrument_id_is_string(self) -> None:
        """instrument_id field should be String."""
        assert INDEX_MEMBER_SOURCE_SCHEMA.schema["instrument_id"] == pl.String

    def test_weight_is_float64(self) -> None:
        """Weight field should be Float64."""
        assert INDEX_MEMBER_SOURCE_SCHEMA.schema["weight"] == pl.Float64

    def test_effective_from_is_date(self) -> None:
        """effective_from field should be Date."""
        assert INDEX_MEMBER_SOURCE_SCHEMA.schema["effective_from"] == pl.Date

    def test_effective_to_is_date(self) -> None:
        """effective_to field should be Date."""
        assert INDEX_MEMBER_SOURCE_SCHEMA.schema["effective_to"] == pl.Date

    def test_has_pit_columns(self) -> None:
        """Schema should have PIT columns."""
        expected = ("effective_from", "effective_to")
        assert INDEX_MEMBER_SOURCE_SCHEMA.pit_columns == expected
