"""Tests for price validator."""

import polars as pl
from ditto_core.data.validators.price import PriceValidator


class TestPriceValidator:
    """Test PriceValidator class."""

    def test_name(self):
        """Test validator name property."""
        validator = PriceValidator()
        assert validator.name == "price_validator"

    def test_valid_ohlc_data(self):
        """Test validation with valid OHLC data."""
        df = pl.DataFrame(
            {
                "date": ["2024-01-01", "2024-01-02"],
                "open": [3.5, 3.6],
                "high": [3.6, 3.7],
                "low": [3.4, 3.5],
                "close": [3.55, 3.65],
            }
        )

        validator = PriceValidator()
        result = validator.validate(df)

        assert result.is_valid
        assert "价格数据正常" in result.message
        assert result.details["total_records"] == 2
        assert result.details["invalid_high"] == 0
        assert result.details["invalid_low"] == 0
        assert result.details["negative_prices"] == 0

    def test_missing_required_columns(self):
        """Test validation with missing required columns."""
        df = pl.DataFrame({"date": ["2024-01-01"], "close": [3.55]})

        validator = PriceValidator()
        result = validator.validate(df)

        assert not result.is_valid
        assert "缺少必需列" in result.message
        assert "open" in result.message
        assert "high" in result.message
        assert "low" in result.message

    def test_negative_prices(self):
        """Test validation with negative prices."""
        df = pl.DataFrame(
            {
                "date": ["2024-01-01"],
                "open": [-3.5],
                "high": [3.6],
                "low": [3.4],
                "close": [3.55],
            }
        )

        validator = PriceValidator()
        result = validator.validate(df)

        assert not result.is_valid
        assert "非正价格" in result.message
        assert result.details["negative_prices"] == 1

    def test_invalid_high_prices(self):
        """Test validation with invalid high prices."""
        df = pl.DataFrame(
            {
                "date": ["2024-01-01"],
                "open": [3.5],
                "high": [3.4],  # High less than open
                "low": [3.3],
                "close": [3.45],
            }
        )

        validator = PriceValidator()
        result = validator.validate(df)

        assert not result.is_valid
        assert "最高价不合理" in result.message
        assert result.details["invalid_high"] == 1

    def test_invalid_low_prices(self):
        """Test validation with invalid low prices."""
        df = pl.DataFrame(
            {
                "date": ["2024-01-01"],
                "open": [3.5],
                "high": [3.6],
                "low": [3.55],  # Low greater than close
                "close": [3.45],
            }
        )

        validator = PriceValidator()
        result = validator.validate(df)

        assert not result.is_valid
        assert "最低价不合理" in result.message
        assert result.details["invalid_low"] == 1

    def test_extreme_price_changes(self):
        """Test validation with extreme price changes."""
        df = pl.DataFrame(
            {
                "date": ["2024-01-01", "2024-01-02"],
                "open": [3.5, 3.5],
                "high": [3.6, 4.4],  # 25% jump
                "low": [3.4, 4.3],
                "close": [3.55, 4.35],  # 22.5% jump
            }
        )

        validator = PriceValidator()
        result = validator.validate(df)

        assert not result.is_valid
        assert "极端价格变化" in result.message
        assert result.details["extreme_changes"] == 1

    def test_multiple_errors(self):
        """Test validation with multiple errors."""
        df = pl.DataFrame(
            {
                "date": ["2024-01-01"],
                "open": [-3.5],  # Negative
                "high": [3.4],  # Too low
                "low": [3.6],  # Too high
                "close": [3.55],
            }
        )

        validator = PriceValidator()
        result = validator.validate(df)

        assert not result.is_valid
        assert "非正价格" in result.message
        assert "最高价不合理" in result.message
        assert "最低价不合理" in result.message

    def test_single_day_no_price_change_check(self):
        """Test that single day data doesn't trigger price change check."""
        df = pl.DataFrame(
            {
                "date": ["2024-01-01"],
                "open": [3.5],
                "high": [3.6],
                "low": [3.4],
                "close": [3.55],
            }
        )

        validator = PriceValidator()
        result = validator.validate(df)

        # Should pass even if extreme change is present
        assert result.is_valid
        assert result.details["extreme_changes"] == 0

    def test_mixed_valid_invalid_records(self):
        """Test validation with mix of valid and invalid records."""
        df = pl.DataFrame(
            {
                "date": ["2024-01-01", "2024-01-02", "2024-01-03"],
                "open": [3.5, -2.0, 4.0],
                "high": [3.6, 2.1, 4.1],
                "low": [3.4, 1.9, 3.9],
                "close": [3.55, 2.0, 4.05],
            }
        )

        validator = PriceValidator()
        result = validator.validate(df)

        assert not result.is_valid
        assert result.details["total_records"] == 3
        assert result.details["negative_prices"] >= 1

    def test_zero_prices(self):
        """Test validation with zero prices."""
        df = pl.DataFrame(
            {
                "date": ["2024-01-01"],
                "open": [0.0],
                "high": [3.6],
                "low": [3.4],
                "close": [3.55],
            }
        )

        validator = PriceValidator()
        result = validator.validate(df)

        assert not result.is_valid
        assert "非正价格" in result.message
        assert result.details["negative_prices"] == 1
