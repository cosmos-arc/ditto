"""Unit tests for market data contracts."""

import pandas as pd
import polars as pl
import pytest
from ditto_foundation.contracts.market_data import (
    AdjustmentFactorSchema,
    DailyPriceSchema,
)


class TestDailyPriceSchema:
    """Test cases for DailyPriceSchema."""

    def test_valid_daily_price_data(self) -> None:
        """Test validation with valid daily price data."""
        # Create test data
        df = pd.DataFrame(
            {
                "symbol": ["510300.SH", "159919.SZ"],
                "trade_date": ["20240101", "20240101"],
                "open_price": [3.5, 4.2],
                "high_price": [3.6, 4.3],
                "low_price": [3.4, 4.1],
                "close_price": [3.55, 4.25],
                "volume": [1000000, 2000000],
                "amount": [3550000.0, 8500000.0],
                "knowledge_date": ["20240102", "20240102"],
            }
        )

        # Should validate successfully
        validated_df = DailyPriceSchema.validate(df)
        assert len(validated_df) == 2

    def test_symbol_format_validation(self) -> None:
        """Test that invalid symbol formats raise validation error."""
        df = pd.DataFrame(
            {
                "symbol": ["INVALID", "159919.SZ"],  # Invalid format for first
                "trade_date": ["20240101", "20240101"],
                "open_price": [3.5, 4.2],
                "high_price": [3.6, 4.3],
                "low_price": [3.4, 4.1],
                "close_price": [3.55, 4.25],
                "volume": [1000000, 2000000],
                "amount": [3550000.0, 8500000.0],
                "knowledge_date": ["20240102", "20240102"],
            }
        )

        with pytest.raises(Exception):  # Pandera raises SchemaErrors
            DailyPriceSchema.validate(df)

    def test_date_format_validation(self) -> None:
        """Test that invalid date formats raise validation error."""
        df = pd.DataFrame(
            {
                "symbol": ["510300.SH", "159919.SZ"],
                "trade_date": ["2024-01-01", "20240101"],  # Mixed format
                "open_price": [3.5, 4.2],
                "high_price": [3.6, 4.3],
                "low_price": [3.4, 4.1],
                "close_price": [3.55, 4.25],
                "volume": [1000000, 2000000],
                "amount": [3550000.0, 8500000.0],
                "knowledge_date": ["20240102", "20240102"],
            }
        )

        with pytest.raises(Exception):
            DailyPriceSchema.validate(df)

    def test_price_validation_non_negative(self) -> None:
        """Test that negative prices raise validation error."""
        df = pd.DataFrame(
            {
                "symbol": ["510300.SH", "159919.SZ"],
                "trade_date": ["20240101", "20240101"],
                "open_price": [-3.5, 4.2],  # Negative price
                "high_price": [3.6, 4.3],
                "low_price": [3.4, 4.1],
                "close_price": [3.55, 4.25],
                "volume": [1000000, 2000000],
                "amount": [3550000.0, 8500000.0],
                "knowledge_date": ["20240102", "20240102"],
            }
        )

        with pytest.raises(Exception):
            DailyPriceSchema.validate(df)

    def test_high_low_price_relationship(self) -> None:
        """Test that high >= max(open, close) and low <= min(open, close)."""
        # Test invalid case where high < close
        df = pd.DataFrame(
            {
                "symbol": ["510300.SH"],
                "trade_date": ["20240101"],
                "open_price": [3.5],
                "high_price": [3.4],  # Lower than open
                "low_price": [3.6],  # Higher than high
                "close_price": [3.55],
                "volume": [1000000],
                "amount": [3550000],
                "knowledge_date": ["20240102"],
            }
        )

        # This should fail the custom validation
        with pytest.raises(Exception):
            DailyPriceSchema.validate(df)

    def test_polars_dataframe_validation(self) -> None:
        """Test validation with Polars DataFrame."""
        df = pl.DataFrame(
            {
                "symbol": ["510300.SH", "159919.SZ"],
                "trade_date": ["20240101", "20240101"],
                "open_price": [3.5, 4.2],
                "high_price": [3.6, 4.3],
                "low_price": [3.4, 4.1],
                "close_price": [3.55, 4.25],
                "volume": [1000000, 2000000],
                "amount": [3550000.0, 8500000.0],
                "knowledge_date": ["20240102", "20240102"],
            }
        )

        # Convert to pandas for validation (Pandera works with pandas)
        validated_df = DailyPriceSchema.validate(df.to_pandas())
        assert len(validated_df) == 2


class TestAdjustmentFactorSchema:
    """Test cases for AdjustmentFactorSchema."""

    def test_valid_adjustment_factor_data(self) -> None:
        """Test validation with valid adjustment factor data."""
        df = pd.DataFrame(
            {
                "symbol": ["510300.SH", "510300.SH"],
                "ex_date": ["20240101", "20240102"],
                "adj_factor": [1.0, 1.1],  # Monotonically increasing
                "adj_type": ["cumulative", "cumulative"],
                "knowledge_date": ["20240102", "20240103"],
            }
        )

        validated_df = AdjustmentFactorSchema.validate(df)
        assert len(validated_df) == 2

    def test_adj_type_validation(self) -> None:
        """Test that invalid adjustment types raise validation error."""
        df = pd.DataFrame(
            {
                "symbol": ["510300.SH"],
                "ex_date": ["20240101"],
                "adj_factor": [1.0],
                "adj_type": ["invalid_type"],  # Not in allowed values
                "knowledge_date": ["20240102"],
            }
        )

        with pytest.raises(Exception):
            AdjustmentFactorSchema.validate(df)

    def test_adj_factor_positive(self) -> None:
        """Test that negative adjustment factors raise validation error."""
        df = pd.DataFrame(
            {
                "symbol": ["510300.SH"],
                "ex_date": ["20240101"],
                "adj_factor": [-1.0],  # Negative factor
                "adj_type": ["cumulative"],
                "knowledge_date": ["20240102"],
            }
        )

        with pytest.raises(Exception):
            AdjustmentFactorSchema.validate(df)

    def test_cumulative_factor_monotonic(self) -> None:
        """Test that cumulative factors are monotonic for each symbol."""
        # Test non-monotonic cumulative factors
        df = pd.DataFrame(
            {
                "symbol": ["510300.SH", "510300.SH"],
                "ex_date": ["20240101", "20240102"],
                "adj_factor": [1.1, 1.0],  # Decreasing (not monotonic)
                "adj_type": ["cumulative", "cumulative"],
                "knowledge_date": ["20240102", "20240103"],
            }
        )

        with pytest.raises(Exception):
            AdjustmentFactorSchema.validate(df)

    def test_mixed_adjustment_types(self) -> None:
        """Test validation with mixed adjustment types."""
        df = pd.DataFrame(
            {
                "symbol": ["510300.SH", "510300.SH"],
                "ex_date": ["20240101", "20240102"],
                "adj_factor": [1.0, 0.9],  # Different factors
                "adj_type": ["cumulative", "point"],  # Different types
                "knowledge_date": ["20240102", "20240103"],
            }
        )

        # Should validate successfully for mixed types
        validated_df = AdjustmentFactorSchema.validate(df)
        assert len(validated_df) == 2

    def test_multiple_symbols(self) -> None:
        """Test validation with multiple symbols."""
        df = pd.DataFrame(
            {
                "symbol": ["510300.SH", "159919.SZ", "510300.SH", "159919.SZ"],
                "ex_date": ["20240101", "20240101", "20240102", "20240102"],
                "adj_factor": [1.0, 1.0, 1.1, 1.05],
                "adj_type": ["cumulative", "cumulative", "cumulative", "cumulative"],
                "knowledge_date": ["20240102", "20240102", "20240103", "20240103"],
            }
        )

        validated_df = AdjustmentFactorSchema.validate(df)
        assert len(validated_df) == 4
