"""
Property-based tests for date utilities in ditto-foundation.

Uses Hypothesis to generate random inputs and verify invariants.
"""

from datetime import date, datetime

from ditto_foundation.util.dates import normalize_date
from hypothesis import given, settings
from hypothesis import strategies as st


class TestNormalizeDateProperties:
    """Property-based tests for normalize_date function."""

    @given(
        st.datetimes(min_value=datetime(2000, 1, 1), max_value=datetime(2100, 12, 31))
    )
    @settings(max_examples=50)
    def test_datetime_to_string_roundtrip(self, dt: datetime) -> None:
        """
        Property: datetime -> normalize -> parse should preserve date part.

        The normalize function should extract the date part from datetime
        and format it consistently, ignoring time components.
        """
        result = normalize_date(dt)
        expected = dt.strftime("%Y-%m-%d")
        assert result == expected

    @given(st.dates(min_value=date(2000, 1, 1), max_value=date(2100, 12, 31)))
    def test_date_to_string_roundtrip(self, d: date) -> None:
        """
        Property: date -> normalize should produce consistent format.

        The normalize function should format dates consistently in YYYY-MM-DD format.
        """
        result = normalize_date(d)
        expected = d.strftime("%Y-%m-%d")
        assert result == expected

    @given(
        st.integers(min_value=2000, max_value=2100),
        st.integers(min_value=1, max_value=12),
        st.integers(min_value=1, max_value=28),
    )
    def test_constructed_dates(self, year: int, month: int, day: int) -> None:
        """
        Property: normalize_date handles valid date constructions.

        Using day 1-28 ensures valid dates across all months.
        """
        d = date(year, month, day)
        result = normalize_date(d)
        assert result == f"{year:04d}-{month:02d}-{day:02d}"

    @given(
        st.datetimes(min_value=datetime(2000, 1, 1), max_value=datetime(2100, 12, 31))
    )
    def test_datetime_time_component_ignored(self, dt: datetime) -> None:
        """
        Property: normalize_date ignores time component of datetime.

        Two datetimes on the same day but different times should normalize
        to same string.
        """
        result1 = normalize_date(dt)
        # Create another datetime on same day but different time
        dt2 = dt.replace(hour=(dt.hour + 12) % 24, minute=(dt.minute + 30) % 60)
        result2 = normalize_date(dt2)
        assert result1 == result2

    @given(
        st.datetimes(min_value=datetime(2000, 1, 1), max_value=datetime(2100, 12, 31)),
        st.datetimes(min_value=datetime(2000, 1, 1), max_value=datetime(2100, 12, 31)),
    )
    def test_same_day_different_time_same_result(
        self, dt1: datetime, dt2: datetime
    ) -> None:
        """
        Property: datetime on same day normalize to same result.

        If two datetimes fall on the same calendar date, they should
        normalize identically.
        """
        # Align to same date
        dt1_aligned = dt1.replace(hour=10, minute=0, second=0)
        dt2_aligned = dt2.replace(
            hour=dt1_aligned.hour,
            minute=dt1_aligned.minute,
            second=dt1_aligned.second,
            day=dt1_aligned.day,
            month=dt1_aligned.month,
            year=dt1_aligned.year,
        )

        result1 = normalize_date(dt1_aligned)
        result2 = normalize_date(dt2_aligned)
        assert result1 == result2

    @given(st.none())
    def test_none_returns_none(self, value: None) -> None:
        """Property: None input returns None output."""
        result = normalize_date(value)
        assert result is None

    @given(st.dates(min_value=date(2000, 1, 1), max_value=date(2100, 12, 31)))
    def test_valid_string_format_preserved(self, d: date) -> None:
        """Property: Valid YYYY-MM-DD strings are preserved as-is."""
        # Convert date to string, then normalize should return same string
        date_str = d.strftime("%Y-%m-%d")
        result = normalize_date(date_str)
        assert result == date_str
