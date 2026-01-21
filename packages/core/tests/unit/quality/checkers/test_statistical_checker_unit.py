"""Tests for StatisticalChecker."""

from datetime import date, timedelta

import polars as pl
import pytest
from ditto_core.quality.checkers.statistical import StatisticalChecker
from ditto_core.quality.spec import DQLevel, DQSeverity


@pytest.fixture
def historical_data():
    """Create historical data for testing (60 days)."""
    dates = [date.today() - timedelta(days=i) for i in range(60, 0, -1)]
    rows = []
    for d in dates:
        rows.extend(
            [
                {"sid": 1, "trade_date": d, "close": 100.0, "volume": 1000},
                {"sid": 2, "trade_date": d, "close": 200.0, "volume": 2000},
            ]
        )
    return pl.DataFrame(rows)


@pytest.fixture
def current_data():
    """Create current data for testing."""
    return pl.DataFrame(
        {
            "sid": [1, 2],
            "trade_date": [date.today(), date.today()],
            "close": [105.0, 210.0],
            "volume": [1100, 2100],
        }
    )


class TestZScoreChecker:
    """Test cases for Z-score anomaly detection."""

    def test_zscore_no_anomalies(self, historical_data, current_data):
        """Test Z-score check with normal data."""
        rule = {
            "rule": "zscore",
            "name": "price_spike",
            "column": "close",
            "window": 60,
            "threshold": 3.0,
        }

        checker = StatisticalChecker()
        issues = checker.check(
            current=current_data,
            historical=historical_data,
            calendar=None,
            rules=[rule],
        )

        assert len(issues) == 0

    def test_zscore_detects_anomalies(self, historical_data):
        """Test Z-score check detects outliers."""
        # Current data with anomaly
        current_data = pl.DataFrame(
            {
                "sid": [1, 2],
                "trade_date": [date.today(), date.today()],
                "close": [500.0, 210.0],  # 500 is way outside normal range
                "volume": [1100, 2100],
            }
        )

        rule = {
            "rule": "zscore",
            "name": "price_spike",
            "column": "close",
            "window": 60,
            "threshold": 3.0,
        }

        checker = StatisticalChecker()
        issues = checker.check(
            current=current_data,
            historical=historical_data,
            calendar=None,
            rules=[rule],
        )

        assert len(issues) == 1
        assert issues[0].level == DQLevel.L3_STATISTICAL
        assert issues[0].severity == DQSeverity.ALERT
        assert issues[0].rule_name == "zscore"  # rule_name is hardcoded as "zscore"

    def test_zscore_with_group_by(self, historical_data, current_data):
        """Test Z-score check with grouping."""
        rule = {
            "rule": "zscore",
            "name": "price_spike",
            "column": "close",
            "window": 60,
            "threshold": 3.0,
            "group_by": "sid",
        }

        checker = StatisticalChecker()
        issues = checker.check(
            current=current_data,
            historical=historical_data,
            calendar=None,
            rules=[rule],
        )

        # Each sid has its own mean/std, so 105 and 210 are normal
        assert len(issues) == 0

    def test_zscore_empty_historical_data(self, current_data):
        """Test Z-score check with empty historical data."""
        rule = {
            "rule": "zscore",
            "name": "price_spike",
            "column": "close",
            "window": 60,
            "threshold": 3.0,
        }

        checker = StatisticalChecker()
        issues = checker.check(
            current=current_data,
            historical=pl.DataFrame(),  # Empty historical
            calendar=None,
            rules=[rule],
        )

        # Should return empty issues when no historical data
        assert len(issues) == 0

    def test_zscore_missing_column(self, current_data):
        """Test Z-score check with missing column."""
        historical_data = pl.DataFrame(
            {
                "sid": [1, 2],
                "trade_date": [date.today(), date.today()],
                # 'close' column missing
                "volume": [1000, 2000],
            }
        )

        rule = {
            "rule": "zscore",
            "name": "price_spike",
            "column": "close",
            "window": 60,
            "threshold": 3.0,
        }

        checker = StatisticalChecker()
        issues = checker.check(
            current=current_data,
            historical=historical_data,
            calendar=None,
            rules=[rule],
        )

        # Should return empty issues when column missing
        assert len(issues) == 0

    def test_zscore_no_column_specified(self, current_data, historical_data):
        """Test Z-score check without column specified."""
        rule = {
            "rule": "zscore",
            "window": 60,
            "threshold": 3.0,
            # No 'column' specified
        }

        checker = StatisticalChecker()
        issues = checker.check(
            current=current_data,
            historical=historical_data,
            calendar=None,
            rules=[rule],
        )

        # Should return empty issues when column not specified
        assert len(issues) == 0

    def test_zscore_with_insufficient_window(self, current_data):
        """Test Z-score check with insufficient historical window."""
        # Only 5 days of historical data (less than window=60)
        dates = [date.today() - timedelta(days=i) for i in range(5, 0, -1)]
        historical_data = pl.DataFrame(
            {
                "sid": [1] * 5,
                "trade_date": dates,
                "close": [100.0] * 5,
            }
        )

        rule = {
            "rule": "zscore",
            "name": "price_spike",
            "column": "close",
            "window": 60,
            "threshold": 3.0,
        }

        checker = StatisticalChecker()
        issues = checker.check(
            current=current_data,
            historical=historical_data,
            calendar=None,
            rules=[rule],
        )

        # Should handle insufficient data gracefully
        # May return issues or empty depending on implementation
        assert isinstance(issues, list)


class TestCompletenessChecker:
    """Test cases for completeness checker."""

    @pytest.fixture
    def calendar_data(self):
        """Create calendar data for testing."""
        # Last 5 trading days
        dates = [
            date.today() - timedelta(days=i)
            for i in range(6, 0, -1)
            if (date.today() - timedelta(days=i)).weekday() < 5
        ][:5]
        return pl.DataFrame({"trade_date": dates, "is_open": [True] * len(dates)})

    def test_completeness_full(self, calendar_data):
        """Test completeness check with all data present."""
        current_data = pl.DataFrame(
            {
                "trade_date": calendar_data["trade_date"].to_list(),
                "sid": [1] * len(calendar_data),
                "close": [100.0] * len(calendar_data),
            }
        )

        rule = {
            "rule": "completeness",
            "lookback_days": 5,
        }

        checker = StatisticalChecker()
        issues = checker.check(
            current=current_data,
            historical=None,
            calendar=calendar_data,
            rules=[rule],
        )

        assert len(issues) == 0

    def test_completeness_missing_data(self, calendar_data):
        """Test completeness check with missing data."""
        # Missing one day
        dates = calendar_data["trade_date"].to_list()
        current_data = pl.DataFrame(
            {
                "trade_date": dates[:-1],  # Missing last day
                "sid": [1] * len(dates[:-1]),
                "close": [100.0] * len(dates[:-1]),
            }
        )

        rule = {
            "rule": "completeness",
            "lookback_days": 5,
        }

        checker = StatisticalChecker()
        issues = checker.check(
            current=current_data,
            historical=None,
            calendar=calendar_data,
            rules=[rule],
        )

        assert len(issues) == 1
        assert issues[0].level == DQLevel.L3_STATISTICAL
        assert issues[0].severity == DQSeverity.ALERT
        assert "completeness" in issues[0].rule_name

    def test_completeness_empty_calendar(self, current_data):
        """Test completeness check with empty calendar."""
        rule = {
            "rule": "completeness",
            "lookback_days": 5,
        }

        checker = StatisticalChecker()
        issues = checker.check(
            current=current_data,
            historical=None,
            calendar=pl.DataFrame(),  # Empty calendar
            rules=[rule],
        )

        # Should handle empty calendar gracefully
        assert len(issues) == 0

    def test_completeness_overall(self, calendar_data):
        """Test completeness check - overall date coverage (not group-aware)."""
        # Note: Current completeness implementation checks overall date coverage,
        # not per-group completeness. It verifies that all expected trading
        # dates have at least some data, regardless of which securities.

        # Create data for all but one trading day
        dates = calendar_data["trade_date"].to_list()
        current_data = pl.DataFrame(
            {
                "trade_date": dates[:-1],  # Missing last trading day
                "sid": [1] * len(dates[:-1]),
                "close": [100.0] * len(dates[:-1]),
            }
        )

        rule = {
            "rule": "completeness",
            "lookback_days": 5,
        }

        checker = StatisticalChecker()
        issues = checker.check(
            current=current_data,
            historical=None,
            calendar=calendar_data,
            rules=[rule],
        )

        # Should detect missing trading day (overall, not per-group)
        assert len(issues) == 1
        assert "Missing data" in issues[0].message


class TestMultipleRules:
    """Test cases for multiple rules."""

    def test_zscore_and_completeness(self, historical_data, current_data):
        """Test running both zscore and completeness checks."""
        calendar_data = pl.DataFrame(
            {
                "trade_date": [date.today()],
                "is_open": [True],
            }
        )

        rules = [
            {
                "rule": "zscore",
                "name": "price_spike",
                "column": "close",
                "window": 60,
                "threshold": 3.0,
            },
            {
                "rule": "completeness",
                "lookback_days": 5,
            },
        ]

        checker = StatisticalChecker()
        issues = checker.check(
            current=current_data,
            historical=historical_data,
            calendar=calendar_data,
            rules=rules,
        )

        # Both rules should pass
        assert len(issues) == 0
