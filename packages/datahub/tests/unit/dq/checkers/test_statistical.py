"""Tests for StatisticalChecker."""

from datetime import date, timedelta
from unittest.mock import MagicMock

import polars as pl
import pytest
from ditto_datahub.dq.checkers.statistical import StatisticalChecker
from ditto_datahub.dq.models import DQLevel, DQSeverity


@pytest.fixture
def mock_hub_with_history():
    """Create mock hub with historical data."""
    hub = MagicMock()

    # Mock historical data (60 days)
    dates = [date.today() - timedelta(days=i) for i in range(60, 0, -1)]
    historical_data = []
    for d in dates:
        historical_data.extend(
            [
                {"sid": 1, "trade_date": d, "close": 100.0},
                {"sid": 2, "trade_date": d, "close": 200.0},
            ]
        )

    hub.bars.get.return_value = pl.DataFrame(historical_data)
    return hub


class TestStatisticalChecker:
    """Test cases for StatisticalChecker."""

    def test_zscore_no_anomalies(self, mock_hub_with_history):
        """Test Z-score check with normal data."""
        trade_date_str = str(date.today())

        rule = {
            "rule": "zscore",
            "column": "close",
            "window": 60,
            "threshold": 3.0,
        }

        checker = StatisticalChecker()
        issues = checker.check(
            "test_dataset", trade_date_str, [rule], mock_hub_with_history
        )

        assert len(issues) == 0

    def test_zscore_detects_anomalies(self, mock_hub_with_history):
        """Test Z-score check detects outliers."""
        trade_date_str = str(date.today())

        # Mock current data with anomaly
        current_data = pl.DataFrame(
            {
                "sid": [1],
                "trade_date": [date.today()],
                "close": [500.0],  # Way outside normal range (100-200)
            }
        )

        # Setup mock to return different data for current date
        def mock_bars_get(start, end, **kwargs):
            if start == end == trade_date_str:
                return current_data
            # Return historical data
            dates = [date.today() - timedelta(days=i) for i in range(60, 0, -1)]
            historical_data = []
            for d in dates:
                historical_data.extend(
                    [
                        {"sid": 1, "trade_date": d, "close": 100.0},
                        {"sid": 2, "trade_date": d, "close": 200.0},
                    ]
                )
            return pl.DataFrame(historical_data)

        mock_hub_with_history.bars.get = mock_bars_get

        rule = {
            "rule": "zscore",
            "column": "close",
            "window": 60,
            "threshold": 3.0,
        }

        checker = StatisticalChecker()
        issues = checker.check(
            "test_dataset", trade_date_str, [rule], mock_hub_with_history
        )

        assert len(issues) == 1
        assert issues[0].level == DQLevel.L3_STATISTICAL
        assert issues[0].severity == DQSeverity.ALERT
        assert "zscore" in issues[0].rule_name

    def test_zscore_with_group_by(self):
        """Test Z-score check with grouping."""
        hub = MagicMock()

        # Create historical data with different stats per sid
        historical_rows = []
        dates = [date.today() - timedelta(days=i) for i in range(60, 0, -1)]
        for d in dates:
            historical_rows.extend(
                [
                    {"sid": 1, "trade_date": d, "close": 100.0},
                    {"sid": 2, "trade_date": d, "close": 200.0},
                ]
            )

        # Current data
        current_data = pl.DataFrame(
            {
                "sid": [1, 2],
                "trade_date": [date.today(), date.today()],
                "close": [105.0, 210.0],  # Both normal relative to their group
            }
        )

        def mock_bars_get(start, end):
            if start == end == str(date.today()):
                return current_data
            return pl.DataFrame(historical_rows)

        hub.bars.get = mock_bars_get

        rule = {
            "rule": "zscore",
            "column": "close",
            "window": 60,
            "threshold": 3.0,
            "group_by": "sid",
        }

        checker = StatisticalChecker()
        issues = checker.check("test_dataset", str(date.today()), [rule], hub)

        assert len(issues) == 0

    def test_zscore_empty_historical_data(self):
        """Test Z-score check with empty historical data."""
        hub = MagicMock()
        hub.bars.get.return_value = pl.DataFrame()

        rule = {
            "rule": "zscore",
            "column": "close",
            "window": 60,
            "threshold": 3.0,
        }

        checker = StatisticalChecker()
        issues = checker.check("test_dataset", str(date.today()), [rule], hub)

        # Should return empty issues when no historical data
        assert len(issues) == 0

    def test_zscore_missing_column(self):
        """Test Z-score check with missing column."""
        hub = MagicMock()
        hub.bars.get.return_value = pl.DataFrame(
            {
                "sid": [1, 2],
                "trade_date": [date.today(), date.today()],
                # 'close' column missing
            }
        )

        rule = {
            "rule": "zscore",
            "column": "close",
            "window": 60,
            "threshold": 3.0,
        }

        checker = StatisticalChecker()
        issues = checker.check("test_dataset", str(date.today()), [rule], hub)

        # Should return empty issues when column missing
        assert len(issues) == 0

    def test_zscore_no_column_specified(self):
        """Test Z-score check without column specified."""
        hub = MagicMock()

        rule = {
            "rule": "zscore",
            "window": 60,
            "threshold": 3.0,
            # No 'column' specified
        }

        checker = StatisticalChecker()
        issues = checker.check("test_dataset", str(date.today()), [rule], hub)

        # Should return empty issues when column not specified
        assert len(issues) == 0


@pytest.fixture
def mock_hub_with_calendar():
    """Create mock hub with calendar data."""
    hub = MagicMock()

    # Mock calendar with 5 trading days
    dates = [
        date.today() - timedelta(days=i)
        for i in range(6, 0, -1)
        if (date.today() - timedelta(days=i)).weekday() < 5
    ]
    calendar_data = [{"trade_date": d, "is_open": True} for d in dates]

    hub.calendar.get.return_value = pl.DataFrame(calendar_data)
    return hub


class TestAssetClassParameter:
    """Test cases for asset_class parameter."""

    def test_zscore_with_asset_class(self):
        """Test Z-score check correctly passes asset_class to hub.bars.get."""
        mock_hub = MagicMock()

        # Mock historical and current data
        historical_data = pl.DataFrame(
            {
                "sid": [1, 2],
                "trade_date": ["2024-01-01", "2024-01-01"],
                "close": [100.0, 200.0],
            }
        )
        current_data = pl.DataFrame(
            {
                "sid": [1],
                "trade_date": ["2024-01-02"],
                "close": [105.0],
            }
        )

        # Use MagicMock's side_effect to track calls
        call_count = [0]
        call_history = []

        def mock_bars_get(start, end, **kwargs):
            call_count[0] += 1
            call_history.append({"start": start, "end": end, "kwargs": kwargs})
            if start == end == "2024-01-02":
                return current_data
            return historical_data

        mock_hub.bars.get = mock_bars_get

        rule = {
            "rule": "zscore",
            "column": "close",
            "window": 60,
            "threshold": 3.0,
        }

        checker = StatisticalChecker()
        checker._check_zscore(
            dataset="stock_daily",
            trade_date="2024-01-02",
            rule=rule,
            hub=mock_hub,
            asset_class="stock",
            market_wide=True,
        )

        # Verify hub.bars.get was called with asset_class parameter
        assert call_count[0] >= 2
        assert len(call_history) >= 2

        # Check first call (historical data)
        first_call = call_history[0]
        assert "asset_class" in first_call["kwargs"]
        assert first_call["kwargs"]["asset_class"] == "stock"
        assert first_call["kwargs"]["market_wide"]

        # Check second call (current data)
        second_call = call_history[1]
        assert "asset_class" in second_call["kwargs"]
        assert second_call["kwargs"]["asset_class"] == "stock"
        assert second_call["kwargs"]["market_wide"]

    def test_completeness_with_asset_class(self):
        """Test completeness check correctly passes asset_class to hub.bars.get."""
        mock_hub = MagicMock()

        # Mock calendar data
        calendar_data = pl.DataFrame(
            {
                "trade_date": ["2024-01-01", "2024-01-02"],
                "is_open": [True, True],
            }
        )

        # Mock bars data
        bars_data = pl.DataFrame(
            {
                "trade_date": ["2024-01-01", "2024-01-02"],
                "close": [100.0, 105.0],
            }
        )

        mock_hub.calendar.get.return_value = calendar_data
        mock_hub.bars.get.return_value = bars_data

        rule = {
            "rule": "completeness",
            "lookback_days": 5,
        }

        checker = StatisticalChecker()
        checker._check_completeness(
            dataset="stock_daily",
            trade_date="2024-01-02",
            rule=rule,
            hub=mock_hub,
            asset_class="stock",
            market_wide=True,
        )

        # Verify hub.bars.get was called with asset_class parameter
        mock_hub.bars.get.assert_called_once()
        call_kwargs = mock_hub.bars.get.call_args.kwargs
        assert "asset_class" in call_kwargs
        assert call_kwargs["asset_class"] == "stock"
        assert call_kwargs["market_wide"]

    def test_check_passes_asset_class_to_rule_checkers(self):
        """Test check() method passes asset_class to individual rule checkers."""
        mock_hub = MagicMock()

        # Mock data to avoid errors
        historical_data = pl.DataFrame(
            {
                "sid": [1, 2],
                "trade_date": ["2024-01-01", "2024-01-01"],
                "close": [100.0, 200.0],
            }
        )

        # Track calls to hub.bars.get
        call_history = []

        def mock_bars_get(start, end, **kwargs):
            call_history.append({"start": start, "end": end, "kwargs": kwargs})
            return historical_data

        mock_hub.bars.get = mock_bars_get

        rules = [
            {
                "rule": "zscore",
                "column": "close",
                "window": 60,
                "threshold": 3.0,
            }
        ]

        checker = StatisticalChecker()
        checker.check(
            dataset="stock_daily",
            trade_date="2024-01-02",
            rules=rules,
            hub=mock_hub,
            asset_class="stock",
            market_wide=True,
        )

        # Verify hub.bars.get was called with asset_class through the entire call chain
        assert len(call_history) > 0
        first_call = call_history[0]
        assert "asset_class" in first_call["kwargs"]
        assert first_call["kwargs"]["asset_class"] == "stock"
        assert first_call["kwargs"]["market_wide"]


class TestCompletenessChecker:
    """Test cases for completeness checker."""

    def test_completeness_full(self, mock_hub_with_calendar):
        """Test completeness check with all data present."""
        # Get the calendar dates
        calendar_dates = mock_hub_with_calendar.calendar.get.return_value[
            "trade_date"
        ].to_list()
        df = pl.DataFrame(
            {
                "trade_date": calendar_dates,
                "close": [100.0] * len(calendar_dates),
            }
        )

        def mock_bars_get(start, end, **kwargs):
            return df

        mock_hub_with_calendar.bars.get = mock_bars_get

        rule = {
            "rule": "completeness",
            "lookback_days": 5,
        }

        checker = StatisticalChecker()
        issues = checker.check(
            "test_dataset", str(date.today()), [rule], mock_hub_with_calendar
        )

        assert len(issues) == 0

    def test_completeness_missing_days(self, mock_hub_with_calendar):
        """Test completeness check with missing trading days."""
        # Create data with only 2 out of expected days
        calendar_dates = mock_hub_with_calendar.calendar.get.return_value[
            "trade_date"
        ].to_list()
        df = pl.DataFrame(
            {
                "trade_date": [
                    calendar_dates[0],
                    calendar_dates[-1],
                ],  # Only first and last day
                "close": [100.0, 200.0],
            }
        )

        def mock_bars_get(start, end, **kwargs):
            return df

        mock_hub_with_calendar.bars.get = mock_bars_get

        rule = {
            "rule": "completeness",
            "lookback_days": 5,
        }

        checker = StatisticalChecker()
        issues = checker.check(
            "test_dataset", str(date.today()), [rule], mock_hub_with_calendar
        )

        assert len(issues) == 1
        assert issues[0].rule_name == "completeness"
        assert "missing" in issues[0].message.lower()

    def test_completeness_no_calendar(self):
        """Test completeness check with no calendar data."""
        hub = MagicMock()
        hub.calendar.get.return_value = pl.DataFrame()

        rule = {
            "rule": "completeness",
            "lookback_days": 5,
        }

        checker = StatisticalChecker()
        issues = checker.check("test_dataset", str(date.today()), [rule], hub)

        # Should return empty issues when no calendar
        assert len(issues) == 0

    def test_completeness_no_data(self, mock_hub_with_calendar):
        """Test completeness check with no actual data."""

        def mock_bars_get(start, end, **kwargs):
            return pl.DataFrame()

        mock_hub_with_calendar.bars.get = mock_bars_get

        rule = {
            "rule": "completeness",
            "lookback_days": 5,
        }

        checker = StatisticalChecker()
        issues = checker.check(
            "test_dataset", str(date.today()), [rule], mock_hub_with_calendar
        )

        assert len(issues) == 1
        assert issues[0].rule_name == "completeness"
        assert (
            "no data" in issues[0].message.lower()
            or "not found" in issues[0].message.lower()
        )


class TestStatisticalCheckerEdgeCases:
    """Test edge cases and error handling for StatisticalChecker."""

    def test_zscore_exception_handling(self):
        """Test Z-score check handles exceptions gracefully."""
        hub = MagicMock()

        # Mock bars.get to raise exception
        hub.bars.get.side_effect = Exception("Database connection failed")

        rule = {
            "rule": "zscore",
            "column": "close",
            "window": 60,
            "threshold": 3.0,
        }

        checker = StatisticalChecker()
        issues = checker.check(
            "test_dataset", "2024-01-01", [rule], hub, asset_class="stock"
        )

        # Should return empty issues on exception
        assert len(issues) == 0

    def test_completeness_exception_handling(self):
        """Test completeness check handles exceptions gracefully."""
        hub = MagicMock()

        # Mock calendar.get to raise exception
        hub.calendar.get.side_effect = Exception("Calendar service unavailable")

        rule = {
            "rule": "completeness",
            "lookback_days": 5,
        }

        checker = StatisticalChecker()
        issues = checker.check(
            "test_dataset", "2024-01-01", [rule], hub, asset_class="stock"
        )

        # Should return empty issues on exception
        assert len(issues) == 0

    def test_unknown_rule_type(self):
        """Test check with unknown rule type."""
        hub = MagicMock()

        rule = {
            "rule": "unknown_rule",
            "param": "value",
        }

        checker = StatisticalChecker()
        issues = checker.check(
            "test_dataset", "2024-01-01", [rule], hub, asset_class="stock"
        )

        # Should return empty issues for unknown rule types
        assert len(issues) == 0

    def test_empty_rules_list(self):
        """Test check with empty rules list."""
        hub = MagicMock()

        checker = StatisticalChecker()
        issues = checker.check(
            "test_dataset", "2024-01-01", [], hub, asset_class="stock"
        )

        assert len(issues) == 0

    def test_multiple_rules_mixed_types(self):
        """Test check with multiple rules of different types."""
        hub = MagicMock()

        # Mock historical data
        dates = [date.today() - timedelta(days=i) for i in range(60, 0, -1)]
        historical_data = [{"sid": 1, "trade_date": d, "close": 100.0} for d in dates]

        # Mock calendar data
        calendar_data = [
            {"trade_date": d, "is_open": d.weekday() < 5}
            for d in [
                date.today() - timedelta(days=i)
                for i in range(10, 0, -1)
                if (date.today() - timedelta(days=i)).weekday() < 5
            ][:5]
        ]

        def mock_bars_get(start, end, **kwargs):
            return pl.DataFrame(historical_data)

        hub.bars.get = mock_bars_get
        hub.calendar.get.return_value = pl.DataFrame(calendar_data)

        rules = [
            {
                "rule": "zscore",
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
            "test_dataset", str(date.today()), rules, hub, asset_class="stock"
        )

        # Should collect issues from both rules
        assert isinstance(issues, list)

    def test_zscore_with_market_wide_false(self):
        """Test zscore check with market_wide=False (default)."""
        hub = MagicMock()

        historical_data = pl.DataFrame(
            {
                "sid": [1, 2],
                "trade_date": ["2024-01-01", "2024-01-01"],
                "close": [100.0, 200.0],
            }
        )

        hub.bars.get.return_value = historical_data

        rule = {
            "rule": "zscore",
            "column": "close",
            "window": 60,
            "threshold": 3.0,
        }

        checker = StatisticalChecker()
        issue = checker._check_zscore(
            dataset="test_dataset",
            trade_date="2024-01-02",
            rule=rule,
            hub=hub,
            asset_class="stock",
            market_wide=False,
        )

        # _check_zscore returns DQIssue | None
        assert issue is None or isinstance(issue, list)

    def test_completeness_with_etf_asset_class(self):
        """Test completeness check with ETF asset class."""
        hub = MagicMock()

        calendar_data = pl.DataFrame(
            {
                "trade_date": ["2024-01-01", "2024-01-02"],
                "is_open": [True, True],
            }
        )

        bars_data = pl.DataFrame(
            {
                "trade_date": ["2024-01-01", "2024-01-02"],
                "close": [100.0, 105.0],
            }
        )

        hub.calendar.get.return_value = calendar_data
        hub.bars.get.return_value = bars_data

        rule = {
            "rule": "completeness",
            "lookback_days": 5,
        }

        checker = StatisticalChecker()
        issue = checker._check_completeness(
            dataset="etf_daily",
            trade_date="2024-01-02",
            rule=rule,
            hub=hub,
            asset_class="etf",
            market_wide=False,
        )

        # _check_completeness returns DQIssue | None
        assert issue is None or isinstance(issue, list)

    def test_zscore_with_index_asset_class(self):
        """Test zscore check with index asset class."""
        hub = MagicMock()

        historical_data = pl.DataFrame(
            {
                "sid": [1],
                "trade_date": ["2024-01-01"],
                "close": [1000.0],
            }
        )

        hub.bars.get.return_value = historical_data

        rule = {
            "rule": "zscore",
            "column": "close",
            "window": 60,
            "threshold": 3.0,
        }

        checker = StatisticalChecker()
        issue = checker._check_zscore(
            dataset="index_daily",
            trade_date="2024-01-02",
            rule=rule,
            hub=hub,
            asset_class="index",
            market_wide=False,
        )

        # _check_zscore returns DQIssue | None
        assert issue is None or isinstance(issue, list)

    def test_zscore_invalid_date_format(self):
        """Test zscore check with invalid date format."""
        hub = MagicMock()

        hub.bars.get.return_value = pl.DataFrame()

        rule = {
            "rule": "zscore",
            "column": "close",
            "window": 60,
            "threshold": 3.0,
        }

        checker = StatisticalChecker()
        issues = checker.check(
            "test_dataset", "invalid-date", [rule], hub, asset_class="stock"
        )

        # Should handle exception gracefully
        assert len(issues) == 0

    def test_completeness_invalid_date_format(self):
        """Test completeness check with invalid date format."""
        hub = MagicMock()

        hub.calendar.get.side_effect = Exception("Invalid date")

        rule = {
            "rule": "completeness",
            "lookback_days": 5,
        }

        checker = StatisticalChecker()
        issues = checker.check(
            "test_dataset", "invalid-date", [rule], hub, asset_class="stock"
        )

        # Should handle exception gracefully
        assert len(issues) == 0
