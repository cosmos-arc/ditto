"""Tests for schema validation."""

from datetime import date

import polars as pl
import pytest
from ditto_datahub.meta.schema_validator import (
    ValidationError,
    validate_dataframe_schema,
)


class TestValidateDataFrameSchema:
    """Tests for validate_dataframe_schema function."""

    def test_validate_passes_for_valid_stock_daily_schema(self) -> None:
        """Test validation passes for valid stock_daily DataFrame."""
        df = pl.DataFrame(
            {
                "instrument_id": [100000001],
                "trade_date": [date(2024, 1, 1)],
                "source": ["tushare"],
                "source_ticker": ["000001.SZ"],
                "open": [10.0],
                "high": [11.0],
                "low": [9.0],
                "close": [10.5],
                "pre_close": [10.0],
                "volume": [1000.0],
                "amount": [10000.0],
                "pct_change": [5.0],
                "turnover": [0.5],
                "is_suspended": [False],
                "is_limit_up": [False],
                "is_limit_down": [False],
                "is_st": [False],
                "up_limit": [11.0],
                "down_limit": [9.0],
            }
        )

        # Should not raise
        validate_dataframe_schema(df, "stock_daily")

    def test_validate_passes_for_valid_adj_factor_schema(self) -> None:
        """Test validation passes for valid adj_factor DataFrame."""
        df = pl.DataFrame(
            {
                "instrument_id": [100000001],
                "trade_date": [date(2024, 1, 1)],
                "source": ["tushare"],
                "source_ticker": ["000001.SZ"],
                "adj_factor": [1.0],
                "knowledge_date": [date(2024, 1, 2)],
            }
        )

        # Should not raise
        validate_dataframe_schema(df, "adj_factor")

    def test_validate_raises_on_missing_required_column(self) -> None:
        """Test validation raises ValidationError for missing column."""
        df = pl.DataFrame(
            {
                "instrument_id": [100000001],
                # Missing "trade_date" column
                "source": ["tushare"],
                "source_ticker": ["000001.SZ"],
            }
        )

        with pytest.raises(ValidationError, match="Missing required columns"):
            validate_dataframe_schema(df, "stock_daily")

    def test_validate_raises_on_wrong_column_type(self) -> None:
        """Test validation raises ValidationError for wrong column type."""
        df = pl.DataFrame(
            {
                "instrument_id": ["not_an_int"],  # Should be Int64
                "trade_date": [date(2024, 1, 1)],
                "source": ["tushare"],
                "source_ticker": ["000001.SZ"],
                "open": [10.0],
                "high": [11.0],
                "low": [9.0],
                "close": [10.5],
                "pre_close": [10.0],
                "volume": [1000.0],
                "amount": [10000.0],
                "pct_change": [5.0],
                "turnover": [0.5],
                "is_suspended": [False],
                "is_limit_up": [False],
                "is_limit_down": [False],
                "is_st": [False],
                "up_limit": [11.0],
                "down_limit": [9.0],
            }
        )

        with pytest.raises(
            ValidationError, match="Column 'instrument_id' has wrong type"
        ):
            validate_dataframe_schema(df, "stock_daily")

    def test_validate_skips_unknown_dataset(self) -> None:
        """Test validation skips validation for unknown dataset."""
        df = pl.DataFrame({"any": ["column"]})

        # Should not raise for unknown datasets
        validate_dataframe_schema(df, "unknown_dataset")

    def test_validate_handles_empty_dataframe(self) -> None:
        """Test validation handles empty DataFrame gracefully."""
        df = pl.DataFrame()

        # Empty DataFrame should fail schema validation
        with pytest.raises(ValidationError, match="Missing required columns"):
            validate_dataframe_schema(df, "stock_daily")
