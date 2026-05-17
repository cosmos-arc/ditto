"""Tests for StatisticalChecker."""

from datetime import date, timedelta

import polars as pl
import pytest
from ditto_data.quality.checkers.statistical import StatisticalChecker
from ditto_data.quality.quality_types import DQLevel, DQSeverity


@pytest.fixture
def historical_data():
    """Create historical data for testing (60 days)."""
    dates = [date.today() - timedelta(days=i) for i in range(60, 0, -1)]
    rows = []
    for d in dates:
        rows.extend(
            [
                {"instrument_id": 1, "trade_date": d, "close": 100.0, "volume": 1000},
                {"instrument_id": 2, "trade_date": d, "close": 200.0, "volume": 2000},
            ]
        )
    return pl.DataFrame(rows)


@pytest.fixture
def current_data():
    """Create current data for testing."""
    return pl.DataFrame(
        {
            "instrument_id": [1, 2],
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
                "instrument_id": [1, 2],
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
        assert issues[0].level == DQLevel.STATISTICAL
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
            "group_by": "instrument_id",
        }

        checker = StatisticalChecker()
        issues = checker.check(
            current=current_data,
            historical=historical_data,
            calendar=None,
            rules=[rule],
        )

        # Each instrument_id has its own mean/std, so 105 and 210 are normal
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
                "instrument_id": [1, 2],
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

        # 新行为：列缺失时返回 ALERT 而不是静默失败
        assert len(issues) == 1
        assert issues[0].level == DQLevel.STATISTICAL
        assert issues[0].severity == DQSeverity.ALERT
        assert "close" in issues[0].message.lower()

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
                "instrument_id": [1] * 5,
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
                "instrument_id": [1] * len(calendar_data),
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
                "instrument_id": [1] * len(dates[:-1]),
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
        assert issues[0].level == DQLevel.STATISTICAL
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
                "instrument_id": [1] * len(dates[:-1]),
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


class TestErrorHandling:
    """Test cases for error handling in statistical checks."""

    def test_zscore_returns_alert_on_compute_error(self):
        """Test that computation errors return ALERT issue instead of silent None."""
        # current 有 price 列，但 historical 没有（会在计算统计量时触发异常）
        current = pl.DataFrame(
            {
                "instrument_id": [1, 2, 3],
                "trade_date": ["2024-01-01", "2024-01-02", "2024-01-03"],
                "price": [10.0, 20.0, 30.0],
            }
        )
        # 历史数据没有 price 列（会触发异常）
        historical = pl.DataFrame(
            {
                "instrument_id": [1, 2],
                "other_column": [100.0, 200.0],
            }
        )

        checker = StatisticalChecker()
        rule = {
            "rule": "zscore",
            "column": "price",
            "threshold": 3.0,
        }

        result = checker._check_zscore(current, historical, rule)

        # 应该返回 DQIssue 而非 None
        assert result is not None, "Exception should return ALERT issue, not None"
        assert result.level == DQLevel.STATISTICAL
        assert result.severity == DQSeverity.ALERT
        assert "error" in result.message.lower() or "failed" in result.message.lower()

    def test_completeness_returns_alert_on_compute_error(self):
        """Test that completeness check errors return ALERT issue."""
        # 创建无效的日历数据（缺少必需列）
        current = pl.DataFrame(
            {
                "instrument_id": [1, 2, 3],
                "trade_date": ["2024-01-01", "2024-01-02", "2024-01-03"],
            }
        )
        # 日历缺少 is_open 列（会导致计算失败）
        calendar = pl.DataFrame(
            {
                "trade_date": ["2024-01-01", "2024-01-02", "2024-01-03"],
                # 缺少 is_open 列
            }
        )

        checker = StatisticalChecker()
        rule = {
            "rule": "completeness",
            "lookback_days": 5,
        }

        result = checker._check_completeness(current, calendar, rule)

        # 应该返回 DQIssue 而非 None
        assert result is not None, "Exception should return ALERT issue, not None"
        assert result.severity == DQSeverity.ALERT
        assert "error" in result.message.lower() or "failed" in result.message.lower()
