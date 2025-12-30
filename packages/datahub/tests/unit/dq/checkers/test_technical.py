"""Tests for TechnicalChecker."""

import polars as pl
from ditto_datahub.dq.checkers.technical import TechnicalChecker
from ditto_datahub.dq.models import DQLevel, DQSeverity


class TestTechnicalChecker:
    """Test cases for TechnicalChecker."""

    def setup_method(self) -> None:
        """Set up test environment."""
        self.checker = TechnicalChecker()

    def test_check_not_null_pass(self) -> None:
        """Test not null check with valid data."""
        df = pl.DataFrame(
            {
                "sid": [1, 2, 3],
                "trade_date": ["2024-01-01", "2024-01-02", "2024-01-03"],
            }
        )

        rules = [
            {
                "rule": "not_null",
                "columns": ["sid", "trade_date"],
                "message": "Required fields",
            }
        ]

        issues = self.checker.check(df, rules)

        assert len(issues) == 0

    def test_check_not_null_fail(self) -> None:
        """Test not null check with null values."""
        df = pl.DataFrame(
            {
                "sid": [1, None, 3],  # One null
                "trade_date": ["2024-01-01", "2024-01-02", "2024-01-03"],
            }
        )

        rules = [{"rule": "not_null", "columns": ["sid"], "message": "SID required"}]

        issues = self.checker.check(df, rules)

        assert len(issues) == 1
        assert issues[0].rule_name == "not_null"
        assert issues[0].severity == DQSeverity.ERROR
        assert issues[0].level == DQLevel.L1_TECHNICAL
        assert issues[0].affected_rows == 1

    def test_check_unique_pass(self) -> None:
        """Test unique check with valid data."""
        df = pl.DataFrame(
            {
                "sid": [1, 1, 2],
                "trade_date": ["2024-01-01", "2024-01-02", "2024-01-01"],
            }
        )

        rules = [
            {
                "rule": "unique",
                "columns": ["sid", "trade_date"],
                "message": "Primary key unique",
            }
        ]

        issues = self.checker.check(df, rules)

        assert len(issues) == 0

    def test_check_unique_fail(self) -> None:
        """Test unique check with duplicates."""
        df = pl.DataFrame(
            {
                "sid": [1, 1, 1],
                "trade_date": [
                    "2024-01-01",
                    "2024-01-02",
                    "2024-01-01",
                ],  # Duplicate (1, 2024-01-01)
            }
        )

        rules = [
            {
                "rule": "unique",
                "columns": ["sid", "trade_date"],
                "message": "Primary key unique",
            }
        ]

        issues = self.checker.check(df, rules)

        assert len(issues) == 1
        assert issues[0].rule_name == "unique"
        assert issues[0].severity == DQSeverity.ERROR
        assert issues[0].level == DQLevel.L1_TECHNICAL
        assert issues[0].affected_rows == 1  # 3 total - 2 unique = 1 duplicate

    def test_check_multiple_issues(self) -> None:
        """Test checking with multiple rule violations."""
        df = pl.DataFrame(
            {
                "sid": [1, None, 1],
                "trade_date": [
                    "2024-01-01",
                    "2024-01-02",
                    "2024-01-01",
                ],  # Null + duplicate
            }
        )

        rules = [
            {"rule": "not_null", "columns": ["sid"], "message": "SID required"},
            {
                "rule": "unique",
                "columns": ["sid", "trade_date"],
                "message": "Primary key unique",
            },
        ]

        issues = self.checker.check(df, rules)

        assert len(issues) == 2
        # Should have both not_null and unique issues
        rule_names = {issue.rule_name for issue in issues}
        assert "not_null" in rule_names
        assert "unique" in rule_names

    def test_check_missing_column(self) -> None:
        """Test checking with missing column."""
        df = pl.DataFrame(
            {
                "sid": [1, 2, 3],
                # trade_date column missing
            }
        )

        rules = [
            {
                "rule": "not_null",
                "columns": ["sid", "trade_date"],
                "message": "Required",
            }
        ]

        issues = self.checker.check(df, rules)

        # Should only check sid column, skip missing trade_date
        assert len(issues) == 0  # All sid values are not null

    def test_check_type_valid(self) -> None:
        """Test type check with valid types."""
        df = pl.DataFrame(
            {
                "sid": [1, 2, 3],
                "close": [10.0, 20.0, 30.0],
                "volume": [100, 200, 300],
            }
        )
        rules = [
            {
                "rule": "type_check",
                "types": {"sid": "Int64", "close": "Float64", "volume": "Int64"},
            }
        ]

        issues = self.checker.check(df, rules)

        assert len(issues) == 0

    def test_check_type_invalid(self) -> None:
        """Test type check with invalid types."""
        df = pl.DataFrame(
            {
                "sid": [1, 2, 3],  # Int64
                "close": ["10.0", "20.0", "30.0"],  # String (wrong)
            }
        )
        rules = [{"rule": "type_check", "types": {"sid": "Int64", "close": "Float64"}}]

        issues = self.checker.check(df, rules)

        assert len(issues) == 1
        assert issues[0].level == DQLevel.L1_TECHNICAL
        assert issues[0].severity == DQSeverity.ERROR
        assert "close" in issues[0].message

    def test_check_type_column_not_exist(self) -> None:
        """Test type check with non-existent column (should skip)."""
        df = pl.DataFrame({"sid": [1, 2, 3]})
        rules = [
            {
                "rule": "type_check",
                "types": {"sid": "Int64", "close": "Float64"},  # close doesn't exist
            }
        ]

        issues = self.checker.check(df, rules)

        assert len(issues) == 0  # Should skip missing columns
