"""Tests for date utilities in ditto-foundation."""

from datetime import date, datetime

import pytest
from ditto_infra.foundation.util.dates import normalize_date


class TestNormalizeDate:
    """Test cases for normalize_date function."""

    def test_normalize_date_with_none(self) -> None:
        """Test normalize_date returns None for None input."""
        result = normalize_date(None)
        assert result is None

    def test_normalize_date_with_valid_string(self) -> None:
        """Test normalize_date with valid YYYY-MM-DD string."""
        result = normalize_date("2024-01-15")
        assert result == "2024-01-15"

    def test_normalize_date_with_datetime(self) -> None:
        """Test normalize_date with datetime object."""
        dt = datetime(2024, 1, 15, 14, 30, 45)
        result = normalize_date(dt)
        assert result == "2024-01-15"

    def test_normalize_date_with_date(self) -> None:
        """Test normalize_date with date object."""
        d = date(2024, 1, 15)
        result = normalize_date(d)
        assert result == "2024-01-15"

    def test_normalize_date_with_invalid_string(self) -> None:
        """Test normalize_date raises ValueError for invalid string."""
        with pytest.raises(ValueError, match="Invalid date format"):
            normalize_date("2024/01/15")

    def test_normalize_date_with_malformed_string(self) -> None:
        """Test normalize_date raises ValueError for malformed string."""
        with pytest.raises(ValueError, match="Invalid date format"):
            normalize_date("not-a-date")

    def test_normalize_date_with_unsupported_type(self) -> None:
        """Test normalize_date raises TypeError for unsupported type."""
        with pytest.raises(TypeError, match="Unsupported date type"):
            normalize_date(20240115)  # type: ignore[arg-type]

    def test_normalize_date_with_datetime_midnight(self) -> None:
        """Test normalize_date with datetime at midnight."""
        dt = datetime(2024, 1, 15, 0, 0, 0)
        result = normalize_date(dt)
        assert result == "2024-01-15"

    def test_normalize_date_with_datetime_end_of_day(self) -> None:
        """Test normalize_date with datetime at end of day."""
        dt = datetime(2024, 1, 15, 23, 59, 59)
        result = normalize_date(dt)
        assert result == "2024-01-15"

    def test_normalize_date_preserves_string_format(self) -> None:
        """Test normalize_date preserves correctly formatted string."""
        original = "2024-12-31"
        result = normalize_date(original)
        assert result == original

    def test_normalize_date_with_leap_year_date(self) -> None:
        """Test normalize_date with leap year date."""
        d = date(2024, 2, 29)  # 2024 is a leap year
        result = normalize_date(d)
        assert result == "2024-02-29"

    def test_normalize_date_with_min_date(self) -> None:
        """Test normalize_date with minimum date."""
        d = date(1, 1, 1)
        result = normalize_date(d)
        assert result == "0001-01-01"

    def test_normalize_date_with_future_date(self) -> None:
        """Test normalize_date with future date."""
        d = date(2099, 12, 31)
        result = normalize_date(d)
        assert result == "2099-12-31"
