"""Tests for volume validator."""

import polars as pl
from ditto_core.data.validators.volume import VolumeValidator


class TestVolumeValidator:
    """Test VolumeValidator class."""

    def test_name(self):
        """Test validator name property."""
        validator = VolumeValidator()
        assert validator.name == "volume_validator"

    def test_valid_volume_data(self):
        """Test validation with valid volume data."""
        df = pl.DataFrame(
            {
                "date": ["2024-01-01", "2024-01-02", "2024-01-03"],
                "volume": [1000000, 1200000, 900000],
            }
        )

        validator = VolumeValidator()
        result = validator.validate(df)

        assert result.is_valid
        assert "成交量数据正常" in result.message
        assert result.details["total_records"] == 3
        assert result.details["negative_volume"] == 0
        assert result.details["extreme_volume"] == 0
        assert result.details["long_zero_volume"] == 0

    def test_missing_volume_column(self):
        """Test validation with missing volume column."""
        df = pl.DataFrame({"date": ["2024-01-01"], "close": [3.55]})

        validator = VolumeValidator()
        result = validator.validate(df)

        assert not result.is_valid
        assert "缺少必需列: volume" in result.message

    def test_negative_volume(self):
        """Test validation with negative volume."""
        df = pl.DataFrame({"date": ["2024-01-01"], "volume": [-1000]})

        validator = VolumeValidator()
        result = validator.validate(df)

        assert not result.is_valid
        assert "负成交量" in result.message
        assert result.details["negative_volume"] == 1

    def test_extreme_volume_spike(self):
        """Test validation with extreme volume spike."""
        # Create data with median volume of 1000, then spike to 60000 (60x)
        df = pl.DataFrame(
            {
                "date": ["2024-01-01", "2024-01-02", "2024-01-03"],
                "volume": [1000, 1100, 60000],  # 60x median
            }
        )

        validator = VolumeValidator()
        result = validator.validate(df)

        assert not result.is_valid
        assert "异常高成交量" in result.message
        assert result.details["extreme_volume"] == 1

    def test_zero_volume_periods(self):
        """Test validation with zero volume periods."""
        df = pl.DataFrame(
            {
                "date": [
                    "2024-01-01",
                    "2024-01-02",
                    "2024-01-03",
                    "2024-01-04",
                    "2024-01-05",
                    "2024-01-06",
                    "2024-01-07",
                    "2024-01-08",
                    "2024-01-09",
                    "2024-01-10",
                    "2024-01-11",
                    "2024-01-12",
                    "2024-01-13",
                    "2024-01-14",
                    "2024-01-15",
                    "2024-01-16",
                ],
                "volume": [1000] + [0] * 15,  # 15 consecutive zero volume days
            }
        )

        validator = VolumeValidator()
        result = validator.validate(df)

        assert not result.is_valid
        assert "长期零成交量" in result.message
        assert result.details["long_zero_volume"] == 1

    def test_short_zero_volume_periods(self):
        """Test that short zero volume periods are valid."""
        df = pl.DataFrame(
            {
                "date": ["2024-01-01", "2024-01-02", "2024-01-03"],
                "volume": [1000, 0, 1100],  # Only 1 zero volume day
            }
        )

        validator = VolumeValidator()
        result = validator.validate(df)

        assert result.is_valid  # Should pass, as zero period is < 10 days
        assert result.details["long_zero_volume"] == 0

    def test_volume_statistics(self):
        """Test volume statistics calculation."""
        df = pl.DataFrame(
            {
                "date": ["2024-01-01", "2024-01-02", "2024-01-03"],
                "volume": [1000, 2000, 3000],
            }
        )

        validator = VolumeValidator()
        result = validator.validate(df)

        stats = result.details["volume_stats"]
        assert stats["min"] == 1000
        assert stats["max"] == 3000
        assert stats["median"] == 2000
        assert stats["mean"] == 2000

    def test_no_date_column_zero_volume_check(self):
        """Test that zero volume check is skipped without date column."""
        df = pl.DataFrame(
            {
                "volume": [0, 0, 1000]  # Zero volumes but no dates
            }
        )

        validator = VolumeValidator()
        result = validator.validate(df)

        # Should pass zero volume check, but might fail other checks
        assert result.details["long_zero_volume"] == 0

    def test_single_record_zero_median(self):
        """Test behavior with single record and zero median."""
        df = pl.DataFrame({"date": ["2024-01-01"], "volume": [0]})

        validator = VolumeValidator()
        result = validator.validate(df)

        # Should not trigger extreme volume check due to zero median
        assert result.details["extreme_volume"] == 0

    def test_all_zero_volumes(self):
        """Test validation with all zero volumes."""
        df = pl.DataFrame(
            {
                "date": [f"2024-01-{i:02d}" for i in range(1, 21)],  # 20 days
                "volume": [0] * 20,  # 20 zero volume days
            }
        )

        validator = VolumeValidator()
        result = validator.validate(df)

        assert not result.is_valid
        assert "长期零成交量" in result.message
        assert result.details["long_zero_volume"] == 1

    def test_mixed_volume_issues(self):
        """Test validation with multiple volume issues."""
        df = pl.DataFrame(
            {
                "date": ["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04"],
                "volume": [1000, -500, 0, 100000],  # Negative, zero, and extreme
            }
        )

        validator = VolumeValidator()
        result = validator.validate(df)

        assert not result.is_valid
        assert result.details["negative_volume"] == 1
        # Other checks depend on median calculation
