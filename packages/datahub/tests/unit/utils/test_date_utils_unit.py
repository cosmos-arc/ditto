"""Tests for date normalization utilities."""

from datetime import date, datetime
from typing import get_args

import pytest
from ditto_foundation.util.dates import DateInput, normalize_date


class TestNormalizeDate:
    """Tests for normalize_date function."""

    def test_normalize_string_date(self) -> None:
        """Test normalize_date handles string dates."""
        result = normalize_date("2024-01-15")
        assert result == "2024-01-15"

    def test_normalize_date_object(self) -> None:
        """Test normalize_date handles date objects."""
        input_date = date(2024, 1, 15)
        result = normalize_date(input_date)
        assert result == "2024-01-15"

    def test_normalize_datetime_object(self) -> None:
        """Test normalize_date handles datetime objects."""
        input_dt = datetime(2024, 1, 15, 10, 30, 45)
        result = normalize_date(input_dt)
        assert result == "2024-01-15"  # Time component discarded

    def test_normalize_none(self) -> None:
        """Test normalize_date handles None."""
        result = normalize_date(None)
        assert result is None

    def test_normalize_invalid_string_raises(self) -> None:
        """Test normalize_date raises ValueError for invalid string."""
        with pytest.raises(ValueError, match="Invalid date format"):
            normalize_date("not-a-date")

    def test_normalize_malformed_string_raises(self) -> None:
        """Test normalize_date raises ValueError for malformed date."""
        with pytest.raises(ValueError, match="Invalid date format"):
            normalize_date("2024/01/15")  # Wrong separator

    def test_date_input_type_exists(self) -> None:
        """Test DateInput type alias is defined."""
        # DateInput should be str | date | datetime | None
        args = get_args(DateInput)
        assert (
            str in args
            or args == (str, date, datetime, type(None))
            or args
            == (
                str,
                date,
                datetime,
                None,
            )
        )
