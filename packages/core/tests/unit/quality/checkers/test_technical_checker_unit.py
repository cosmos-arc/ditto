"""Tests for TechnicalChecker."""

import polars as pl
import pytest
from ditto_core.quality.checkers.technical import TechnicalChecker
from ditto_core.quality.spec import DQLevel, DQSeverity


class TestTechnicalChecker:
    """Test cases for TechnicalChecker."""

    def setup_method(self) -> None:
        """Set up test environment."""
        self.checker = TechnicalChecker()

    @pytest.mark.parametrize(
        (
            "data_dict",
            "rules",
            "expected_issue_count",
            "expected_severity",
            "expected_affected_rows",
        ),
        [
            # Pass case: all values are not null
            (
                {
                    "sid": [1, 2, 3],
                    "trade_date": ["2024-01-01", "2024-01-02", "2024-01-03"],
                },
                [
                    {
                        "rule": "not_null",
                        "columns": ["sid", "trade_date"],
                        "message": "Required fields",
                    }
                ],
                0,
                None,
                None,
            ),
            # Fail case: null values present
            (
                {
                    "sid": [1, None, 3],
                    "trade_date": ["2024-01-01", "2024-01-02", "2024-01-03"],
                },
                [{"rule": "not_null", "columns": ["sid"], "message": "SID required"}],
                1,
                DQSeverity.ERROR,
                1,
            ),
        ],
    )
    def test_check_not_null(
        self,
        data_dict: dict,
        rules: list[dict],
        expected_issue_count: int,
        expected_severity: DQSeverity | None,
        expected_affected_rows: int | None,
    ) -> None:
        """Test not null check with valid and null data."""
        df = pl.DataFrame(data_dict)
        issues = self.checker.check(df, rules)

        assert len(issues) == expected_issue_count
        if expected_issue_count > 0:
            assert issues[0].rule_name == "not_null"
            assert issues[0].severity == expected_severity
            assert issues[0].level == DQLevel.TECHNICAL
            assert issues[0].affected_rows == expected_affected_rows

    @pytest.mark.parametrize(
        (
            "data_dict",
            "rules",
            "expected_issue_count",
            "expected_severity",
            "expected_affected_rows",
        ),
        [
            # Pass case: unique combinations
            (
                {
                    "sid": [1, 1, 2],
                    "trade_date": ["2024-01-01", "2024-01-02", "2024-01-01"],
                },
                [
                    {
                        "rule": "unique",
                        "columns": ["sid", "trade_date"],
                        "message": "Primary key unique",
                    }
                ],
                0,
                None,
                None,
            ),
            # Fail case: duplicate (1, 2024-01-01)
            (
                {
                    "sid": [1, 1, 1],
                    "trade_date": ["2024-01-01", "2024-01-02", "2024-01-01"],
                },
                [
                    {
                        "rule": "unique",
                        "columns": ["sid", "trade_date"],
                        "message": "Primary key unique",
                    }
                ],
                1,
                DQSeverity.ERROR,
                1,
            ),
        ],
    )
    def test_check_unique(
        self,
        data_dict: dict,
        rules: list[dict],
        expected_issue_count: int,
        expected_severity: DQSeverity | None,
        expected_affected_rows: int | None,
    ) -> None:
        """Test unique check with valid and duplicate data."""
        df = pl.DataFrame(data_dict)
        issues = self.checker.check(df, rules)

        assert len(issues) == expected_issue_count
        if expected_issue_count > 0:
            assert issues[0].rule_name == "unique"
            assert issues[0].severity == expected_severity
            assert issues[0].level == DQLevel.TECHNICAL
            assert issues[0].affected_rows == expected_affected_rows

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

    def test_check_empty_dataframe(self) -> None:
        """Test checking with empty dataframe."""
        df = pl.DataFrame(
            {
                "sid": [],
                "trade_date": [],
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

        # Empty dataframe should pass
        assert len(issues) == 0
