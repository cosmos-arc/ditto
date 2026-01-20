"""Tests for BusinessChecker."""

import polars as pl
from ditto_datahub.dq.checkers.business import BusinessChecker
from ditto_datahub.models import DQLevel, DQSeverity


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
        assert issues[0].level == DQLevel.L2_BUSINESS
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
        """Test positive check with column not in dataframe."""
        df = pl.DataFrame(
            {
                "sid": [1, 2, 3],
                "open": [10.0, 20.0, 30.0],  # close column missing
            }
        )

        rules = [
            {
                "rule": "positive",
                "columns": ["open", "close"],  # close doesn't exist
                "message": "Prices must be positive",
            }
        ]

        issues = self.checker.check(df, rules)

        # Should skip missing column and only check existing column
        assert len(issues) == 0

    def test_check_positive_multiple_columns_first_fails(self) -> None:
        """Test positive check with multiple columns where first fails."""
        df = pl.DataFrame(
            {
                "sid": [1, 2, 3],
                "open": [10.0, -5.0, 30.0],  # First column has negative
                "close": [10.5, 20.5, 30.5],
                "high": [11.0, 21.0, 31.0],
            }
        )

        rules = [
            {
                "rule": "positive",
                "columns": ["open", "close", "high"],
                "message": "Prices must be positive",
            }
        ]

        issues = self.checker.check(df, rules)

        # Should return issue for first failing column (open)
        assert len(issues) == 1
        assert issues[0].rule_name == "positive"
        assert issues[0].affected_rows == 1

    def test_check_expression_non_ohlc_name(self) -> None:
        """Test expression check with non-OHLC name."""
        df = pl.DataFrame({"sid": [1, 2], "value": [10.0, 20.0]})

        rules = [
            {
                "rule": "expression",
                "name": "some_other_expression",  # Not containing "ohlc"
                "expr": "value > 0",
                "message": "Custom expression",
            }
        ]

        issues = self.checker.check(df, rules)

        # Should return None for non-OHLC expressions
        assert len(issues) == 0

    def test_check_expression_ohlc_missing_columns(self) -> None:
        """Test OHLC expression check with missing required columns."""
        df = pl.DataFrame(
            {
                "sid": [1, 2],
                "open": [10.0, 20.0],
                "high": [10.5, 20.8],
                # Missing low and close
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

        # Should return None when required columns are missing
        assert len(issues) == 0

    def test_check_range_column_not_exist(self) -> None:
        """Test range check with column not in dataframe."""
        df = pl.DataFrame({"sid": [1, 2, 3]})  # weight column missing

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

        # Should return None when column doesn't exist
        assert len(issues) == 0

    def test_check_range_only_min(self) -> None:
        """Test range check with only min value specified."""
        df = pl.DataFrame(
            {
                "sid": [1, 2, 3],
                "value": [-0.5, 0.3, 0.4],  # One below min
            }
        )

        rules = [
            {
                "rule": "range_check",
                "column": "value",
                "min": 0.0,
                # No max specified
                "message": "Value out of range",
            }
        ]

        issues = self.checker.check(df, rules)

        assert len(issues) == 1
        assert issues[0].rule_name == "range_check"
        assert issues[0].affected_rows == 1

    def test_check_range_only_max(self) -> None:
        """Test range check with only max value specified."""
        df = pl.DataFrame(
            {
                "sid": [1, 2, 3],
                "value": [0.3, 1.5, 0.4],  # One above max
            }
        )

        rules = [
            {
                "rule": "range_check",
                "column": "value",
                # No min specified
                "max": 1.0,
                "message": "Value out of range",
            }
        ]

        issues = self.checker.check(df, rules)

        assert len(issues) == 1
        assert issues[0].rule_name == "range_check"
        assert issues[0].affected_rows == 1

    def test_check_range_no_bounds(self) -> None:
        """Test range check with no min or max specified."""
        df = pl.DataFrame({"sid": [1, 2, 3], "value": [0.3, -0.1, 1.5]})

        rules = [
            {
                "rule": "range_check",
                "column": "value",
                # No min or max specified
                "message": "Value out of range",
            }
        ]

        issues = self.checker.check(df, rules)

        # Should return None when no bounds specified
        assert len(issues) == 0

    def test_check_no_zero_volume_column_not_exist(self) -> None:
        """Test no zero volume check with column not in dataframe."""
        df = pl.DataFrame({"sid": [1, 2, 3]})  # volume column missing

        rules = [
            {"rule": "no_zero_volume", "column": "volume", "message": "Volume is zero"}
        ]

        issues = self.checker.check(df, rules)

        # Should return None when column doesn't exist
        assert len(issues) == 0

    def test_check_unknown_rule_type(self) -> None:
        """Test check with unknown rule type."""
        df = pl.DataFrame({"sid": [1, 2, 3], "value": [10.0, 20.0, 30.0]})

        rules = [
            {
                "rule": "unknown_rule",  # Unknown rule type
                "message": "Unknown rule",
            }
        ]

        issues = self.checker.check(df, rules)

        # Should return None for unknown rule types
        assert len(issues) == 0

    def test_check_with_context(self) -> None:
        """Test check with context parameter."""
        df = pl.DataFrame({"sid": [1, 2, 3], "value": [10.0, 20.0, 30.0]})

        rules = [
            {
                "rule": "positive",
                "columns": ["value"],
                "message": "Value must be positive",
            }
        ]

        context = {"dataset": "test_dataset", "source": "api"}

        issues = self.checker.check(df, rules, context)

        # Context should be passed but not used in positive check
        assert len(issues) == 0

    def test_check_empty_rules_list(self) -> None:
        """Test check with empty rules list."""
        df = pl.DataFrame({"sid": [1, 2, 3], "value": [10.0, 20.0, 30.0]})

        issues = self.checker.check(df, [])

        assert len(issues) == 0

    def test_check_multiple_rules(self) -> None:
        """Test check with multiple rules."""
        df = pl.DataFrame(
            {
                "sid": [1, 2, 3],
                "value": [-5.0, 1.5, 0.5],  # Negative and out of range
                "volume": [1000, 0, 3000],  # One zero
            }
        )

        rules = [
            {
                "rule": "positive",
                "columns": ["value"],
                "message": "Value positive",
            },
            {
                "rule": "range_check",
                "column": "value",
                "min": 0.0,
                "max": 1.0,
                "message": "Value range",
            },
            {
                "rule": "no_zero_volume",
                "column": "volume",
                "message": "No zero volume",
            },
        ]

        issues = self.checker.check(df, rules)

        # Should collect issues from all rules
        assert len(issues) == 3
        rule_names = {issue.rule_name for issue in issues}
        assert "positive" in rule_names
        assert "range_check" in rule_names
        assert "no_zero_volume" in rule_names
