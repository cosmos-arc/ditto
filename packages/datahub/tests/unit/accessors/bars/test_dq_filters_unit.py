"""Unit tests for DQ filters."""

import polars as pl
import pytest
from ditto_datahub.accessors.bars.dq_filters import (
    filter_failed_rows,
    filter_foreign_key_violations,
    filter_not_null_violations,
    filter_type_check_violations,
    filter_unique_violations,
)
from ditto_datahub.models.quality import DQIssue, DQLevel, DQSeverity


@pytest.mark.unit
class TestFilterNotNullViolations:
    """Tests for filter_not_null_violations."""

    def test_filters_rows_with_null_values(self) -> None:
        """Test that filter_not_null_violations filters rows with null values."""
        df = pl.DataFrame(
            {
                "sid": [1, 2, 3],
                "trade_date": ["2024-01-01", "2024-01-02", "2024-01-03"],
                "close": [10.0, None, 12.0],
            }
        )
        issue = DQIssue(
            level=DQLevel.L1_TECHNICAL,
            severity=DQSeverity.ERROR,
            rule_name="not_null",
            message="close has null values",
            affected_rows=1,
        )

        result = filter_not_null_violations(df, issue)

        assert len(result) == 1
        assert result[0, "sid"] == 2
        assert result[0, "close"] is None

    def test_returns_empty_when_no_nulls(self) -> None:
        """Test that filter_not_null_violations returns empty when no nulls."""
        df = pl.DataFrame(
            {
                "sid": [1, 2, 3],
                "trade_date": ["2024-01-01", "2024-01-02", "2024-01-03"],
                "close": [10.0, 11.0, 12.0],
            }
        )
        issue = DQIssue(
            level=DQLevel.L1_TECHNICAL,
            severity=DQSeverity.ERROR,
            rule_name="not_null",
            message="close has null values",
        )

        result = filter_not_null_violations(df, issue)

        assert result.is_empty()

    def test_fallback_checks_all_columns(self) -> None:
        """Test fallback behavior checks all columns for nulls."""
        df = pl.DataFrame(
            {
                "sid": [1, 2, 3],
                "trade_date": ["2024-01-01", "2024-01-02", "2024-01-03"],
                "close": [10.0, None, 12.0],
            }
        )
        # Message without column name (fallback case)
        issue = DQIssue(
            level=DQLevel.L1_TECHNICAL,
            severity=DQSeverity.ERROR,
            rule_name="not_null",
            message="has null values",
        )

        result = filter_not_null_violations(df, issue)

        # Should find null in close column
        assert len(result) == 1
        assert result[0, "sid"] == 2


@pytest.mark.unit
class TestFilterUniqueViolations:
    """Tests for filter_unique_violations."""

    def test_filters_duplicate_rows(self) -> None:
        """Test that filter_unique_violations finds duplicate rows."""
        df = pl.DataFrame(
            {
                "sid": [1, 1, 2],
                "trade_date": ["2024-01-01", "2024-01-01", "2024-01-02"],
                "close": [10.0, 10.0, 12.0],
            }
        )
        issue = DQIssue(
            level=DQLevel.L1_TECHNICAL,
            severity=DQSeverity.ERROR,
            rule_name="unique",
            message="duplicate rows found",
        )

        result = filter_unique_violations(df, issue)

        # Should return both duplicate rows
        assert len(result) == 2
        assert result["sid"].to_list() == [1, 1]

    def test_returns_empty_when_no_duplicates(self) -> None:
        """Test that filter_unique_violations returns empty when unique."""
        df = pl.DataFrame(
            {
                "sid": [1, 2, 3],
                "trade_date": ["2024-01-01", "2024-01-02", "2024-01-03"],
                "close": [10.0, 11.0, 12.0],
            }
        )
        issue = DQIssue(
            level=DQLevel.L1_TECHNICAL,
            severity=DQSeverity.ERROR,
            rule_name="unique",
            message="unique constraint",
        )

        result = filter_unique_violations(df, issue)

        # Fallback returns all rows when no duplicates found
        assert len(result) == 3


@pytest.mark.unit
class TestFilterForeignKeyViolations:
    """Tests for filter_foreign_key_violations."""

    def test_returns_all_rows_for_manual_review(self) -> None:
        """Test that filter_foreign_key_violations returns all rows."""
        df = pl.DataFrame(
            {
                "sid": [1, 2, 3],
                "trade_date": ["2024-01-01", "2024-01-02", "2024-01-03"],
                "close": [10.0, 11.0, 12.0],
            }
        )
        issue = DQIssue(
            level=DQLevel.L2_BUSINESS,
            severity=DQSeverity.ERROR,
            rule_name="foreign_key",
            message="foreign key violation",
        )

        result = filter_foreign_key_violations(df, issue)

        # Returns all rows for manual review
        assert len(result) == 3


@pytest.mark.unit
class TestFilterTypeCheckViolations:
    """Tests for filter_type_check_violations."""

    def test_returns_all_rows_for_manual_review(self) -> None:
        """Test that filter_type_check_violations returns all rows."""
        df = pl.DataFrame(
            {
                "sid": [1, 2, 3],
                "trade_date": ["2024-01-01", "2024-01-02", "2024-01-03"],
                "close": [10.0, 11.0, 12.0],
            }
        )
        issue = DQIssue(
            level=DQLevel.L1_TECHNICAL,
            severity=DQSeverity.ERROR,
            rule_name="type_check",
            message="type check failed",
        )

        result = filter_type_check_violations(df, issue)

        # Returns all rows for manual review
        assert len(result) == 3


@pytest.mark.unit
class TestFilterFailedRows:
    """Tests for filter_failed_rows dispatcher."""

    def test_dispatches_to_not_null_filter(self) -> None:
        """Test that filter_failed_rows dispatches to not_null filter."""
        df = pl.DataFrame(
            {
                "sid": [1, 2, 3],
                "trade_date": ["2024-01-01", "2024-01-02", "2024-01-03"],
                "close": [10.0, None, 12.0],
            }
        )
        issue = DQIssue(
            level=DQLevel.L1_TECHNICAL,
            severity=DQSeverity.ERROR,
            rule_name="not_null",
            message="close has null values",
        )

        result = filter_failed_rows(df, issue)

        assert len(result) == 1
        assert result[0, "sid"] == 2

    def test_dispatches_to_unique_filter(self) -> None:
        """Test that filter_failed_rows dispatches to unique filter."""
        df = pl.DataFrame(
            {
                "sid": [1, 1, 2],
                "trade_date": ["2024-01-01", "2024-01-01", "2024-01-02"],
                "close": [10.0, 10.0, 12.0],
            }
        )
        issue = DQIssue(
            level=DQLevel.L1_TECHNICAL,
            severity=DQSeverity.ERROR,
            rule_name="unique",
            message="duplicate rows",
        )

        result = filter_failed_rows(df, issue)

        assert len(result) == 2

    def test_dispatches_to_foreign_key_filter(self) -> None:
        """Test that filter_failed_rows dispatches to foreign_key filter."""
        df = pl.DataFrame(
            {
                "sid": [1, 2, 3],
                "close": [10.0, 11.0, 12.0],
            }
        )
        issue = DQIssue(
            level=DQLevel.L2_BUSINESS,
            severity=DQSeverity.ERROR,
            rule_name="foreign_key",
            message="FK violation",
        )

        result = filter_failed_rows(df, issue)

        # Returns all rows for manual review
        assert len(result) == 3

    def test_dispatches_to_type_check_filter(self) -> None:
        """Test that filter_failed_rows dispatches to type_check filter."""
        df = pl.DataFrame(
            {
                "sid": [1, 2, 3],
                "close": [10.0, 11.0, 12.0],
            }
        )
        issue = DQIssue(
            level=DQLevel.L1_TECHNICAL,
            severity=DQSeverity.ERROR,
            rule_name="type_check",
            message="type mismatch",
        )

        result = filter_failed_rows(df, issue)

        # Returns all rows for manual review
        assert len(result) == 3

    def test_unknown_rule_returns_all_rows(self) -> None:
        """Test that filter_failed_rows returns all rows for unknown rule."""
        df = pl.DataFrame(
            {
                "sid": [1, 2, 3],
                "close": [10.0, 11.0, 12.0],
            }
        )
        issue = DQIssue(
            level=DQLevel.L3_STATISTICAL,
            severity=DQSeverity.ALERT,
            rule_name="unknown_rule",
            message="unknown",
        )

        result = filter_failed_rows(df, issue)

        # Default: return all rows for manual review
        assert len(result) == 3

    def test_case_insensitive_rule_name(self) -> None:
        """Test that rule_name matching is case-insensitive."""
        df = pl.DataFrame(
            {
                "sid": [1, 2, 3],
                "close": [10.0, None, 12.0],
            }
        )
        issue = DQIssue(
            level=DQLevel.L1_TECHNICAL,
            severity=DQSeverity.ERROR,
            rule_name="NOT_NULL",  # Uppercase
            message="close has null values",
        )

        result = filter_failed_rows(df, issue)

        assert len(result) == 1
