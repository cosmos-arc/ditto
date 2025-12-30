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
        def mock_bars_get(start, end):
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
