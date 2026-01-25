"""Tests for BusinessChecker."""

import polars as pl
from ditto_core.quality.checkers.business import BusinessChecker
from ditto_core.quality.spec import DQLevel, DQSeverity


class TestBusinessChecker:
    """Test cases for BusinessChecker."""

    def setup_method(self) -> None:
        """Set up test environment."""
        self.checker = BusinessChecker()

    def test_check_positive_values_pass(self) -> None:
        """Test positive check with valid data."""
        df = pl.DataFrame(
            {
                "sid": [1, 2, 3],
                "open": [10.0, 20.0, 30.0],
                "close": [10.5, 20.5, 30.5],
            }
        )

        rules = [
            {
                "rule": "positive",
                "columns": ["open", "close"],
                "message": "Prices must be positive",
            }
        ]

        issues = self.checker.check(df, rules)

        assert len(issues) == 0

    def test_check_positive_values_fail(self) -> None:
        """Test positive check with negative values."""
        df = pl.DataFrame(
            {
                "sid": [1, 2, 3],
                "open": [10.0, -5.0, 30.0],  # One negative
                "close": [10.5, 20.5, 30.5],
            }
        )

        rules = [
            {
                "rule": "positive",
                "columns": ["open", "close"],
                "message": "Prices must be positive",
            }
        ]

        issues = self.checker.check(df, rules)

        assert len(issues) == 1
        assert issues[0].rule_name == "positive"
        assert issues[0].severity == DQSeverity.WARNING
        assert issues[0].level == DQLevel.BUSINESS
        assert issues[0].affected_rows == 1

    def test_check_ohlc_consistency_pass(self) -> None:
        """Test OHLC consistency check with valid data."""
        df = pl.DataFrame(
            {
                "sid": [1, 2],
                "open": [10.0, 20.0],
                "high": [10.5, 20.8],
                "low": [9.8, 19.5],
                "close": [10.2, 20.5],
            }
        )

        rules = [
            {
                "rule": "expression",
                "name": "ohlc_consistency",
                "expr": "high >= low",
                "message": "OHLC relationship violated",
            }
        ]

        issues = self.checker.check(df, rules)

        assert len(issues) == 0

    def test_check_ohlc_consistency_fail(self) -> None:
        """Test OHLC consistency check with invalid data."""
        df = pl.DataFrame(
            {
                "sid": [1, 2],
                "open": [10.5, 20.0],
                "high": [10.0, 14.0],  # high < open
                "low": [10.8, 16.0],  # low > open
                "close": [10.1, 15.5],
            }
        )

        rules = [
            {
                "rule": "expression",
                "name": "ohlc_consistency",
                "expr": "high >= low",
                "message": "OHLC relationship violated",
            }
        ]

        issues = self.checker.check(df, rules)

        assert len(issues) == 1
        assert issues[0].rule_name == "ohlc_consistency"
        assert issues[0].severity == DQSeverity.WARNING
        assert issues[0].affected_rows == 2

    def test_check_range_pass(self) -> None:
        """Test range check with valid data."""
        df = pl.DataFrame(
            {
                "sid": [1, 2, 3],
                "weight": [0.3, 0.4, 0.3],  # All in [0, 1]
            }
        )

        rules = [
            {
                "rule": "range_check",
                "column": "weight",
                "min": 0.0,
                "max": 1.0,
                "message": "Weight out of range",
            }
        ]

        issues = self.checker.check(df, rules)

        assert len(issues) == 0

    def test_check_range_fail(self) -> None:
        """Test range check with invalid data."""
        df = pl.DataFrame(
            {
                "sid": [1, 2, 3],
                "weight": [0.3, -0.1, 1.5],  # Two out of range
            }
        )

        rules = [
            {
                "rule": "range_check",
                "column": "weight",
                "min": 0.0,
                "max": 1.0,
                "message": "Weight out of range",
            }
        ]

        issues = self.checker.check(df, rules)

        assert len(issues) == 1
        assert issues[0].rule_name == "range_check"
        assert issues[0].affected_rows == 2

    def test_check_no_zero_volume_pass(self) -> None:
        """Test no zero volume check with valid data."""
        df = pl.DataFrame(
            {
                "sid": [1, 2, 3],
                "volume": [1000, 2000, 3000],
            }
        )

        rules = [
            {"rule": "no_zero_volume", "column": "volume", "message": "Volume is zero"}
        ]

        issues = self.checker.check(df, rules)

        assert len(issues) == 0

    def test_check_no_zero_volume_fail(self) -> None:
        """Test no zero volume check with zero values."""
        df = pl.DataFrame(
            {
                "sid": [1, 2, 3],
                "volume": [1000, 0, 3000],  # One zero
            }
        )

        rules = [
            {"rule": "no_zero_volume", "column": "volume", "message": "Volume is zero"}
        ]

        issues = self.checker.check(df, rules)

        assert len(issues) == 1
        assert issues[0].rule_name == "no_zero_volume"
        assert issues[0].affected_rows == 1

    def test_check_positive_missing_column(self) -> None:
        """Test positive check with missing column."""
        df = pl.DataFrame(
            {
                "sid": [1, 2, 3],
                # open column missing
                "close": [10.5, 20.5, 30.5],
            }
        )

        rules = [
            {
                "rule": "positive",
                "columns": ["open", "close"],
                "message": "Prices must be positive",
            }
        ]

        issues = self.checker.check(df, rules)

        # Should only check close column, skip missing open
        assert len(issues) == 0  # All close values are positive
