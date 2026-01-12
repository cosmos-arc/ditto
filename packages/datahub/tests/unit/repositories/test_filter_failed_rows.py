"""Tests for filter_failed_rows function."""

import polars as pl
from ditto_datahub.dq.models import DQIssue, DQLevel, DQSeverity
from ditto_datahub.repositories.bars import filter_failed_rows


class TestFilterFailedRowsNotNull:
    """Tests for not_null rule filtering."""

    def test_filters_null_values_in_single_column(self) -> None:
        """Test filtering null values in a single column."""
        # Arrange
        df = pl.DataFrame(
            {
                "sid": [1, 2, 3, 4],
                "trade_date": ["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04"],
                "close": [10.0, None, 12.0, 13.0],
            }
        )
        issue = DQIssue(
            level=DQLevel.L1_TECHNICAL,
            severity=DQSeverity.ERROR,
            rule_name="not_null",
            message="close has null values",
            affected_rows=1,
        )

        # Act
        result = filter_failed_rows(df, issue)

        # Assert
        assert len(result) == 1
        assert result["sid"][0] == 2
        assert result["close"][0] is None

    def test_filters_null_values_in_multiple_columns(self) -> None:
        """Test filtering null values across multiple columns."""
        # Arrange
        df = pl.DataFrame(
            {
                "sid": [1, 2, 3, 4],
                "close": [10.0, None, 12.0, None],
                "open": [9.0, 10.0, None, 13.0],
            }
        )
        issue = DQIssue(
            level=DQLevel.L1_TECHNICAL,
            severity=DQSeverity.ERROR,
            rule_name="not_null",
            message="close has null values",
            affected_rows=2,
        )

        # Act
        result = filter_failed_rows(df, issue)

        # Assert
        assert len(result) == 2
        assert set(result["sid"].to_list()) == {2, 4}

    def test_case_insensitive_column_matching(self) -> None:
        """Test that column matching is case-insensitive."""
        # Arrange
        df = pl.DataFrame(
            {
                "SID": [1, 2, 3],
                "Close": [10.0, None, 12.0],
            }
        )
        issue = DQIssue(
            level=DQLevel.L1_TECHNICAL,
            severity=DQSeverity.ERROR,
            rule_name="not_null",
            message="close has null values",
            affected_rows=1,
        )

        # Act
        result = filter_failed_rows(df, issue)

        # Assert
        assert len(result) == 1
        assert result["SID"][0] == 2

    def test_fallback_to_any_null_when_column_not_found(self) -> None:
        """Test fallback behavior when column name not in message."""
        # Arrange
        df = pl.DataFrame(
            {
                "sid": [1, 2, 3],
                "close": [10.0, None, 12.0],
            }
        )
        issue = DQIssue(
            level=DQLevel.L1_TECHNICAL,
            severity=DQSeverity.ERROR,
            rule_name="not_null",
            message="Some null values detected",
            affected_rows=1,
        )

        # Act
        result = filter_failed_rows(df, issue)

        # Assert
        assert len(result) == 1
        assert result["sid"][0] == 2


class TestFilterFailedRowsUnique:
    """Tests for unique rule filtering."""

    def test_filters_duplicate_rows(self) -> None:
        """Test filtering duplicate rows."""
        # Arrange
        df = pl.DataFrame(
            {
                "sid": [1, 1, 2, 3],
                "trade_date": ["2024-01-01", "2024-01-01", "2024-01-02", "2024-01-03"],
                "close": [10.0, 10.0, 11.0, 12.0],
            }
        )
        issue = DQIssue(
            level=DQLevel.L1_TECHNICAL,
            severity=DQSeverity.ERROR,
            rule_name="unique",
            message="Duplicate rows found",
            affected_rows=2,
        )

        # Act
        result = filter_failed_rows(df, issue)

        # Assert
        assert len(result) == 2
        assert result["sid"][0] == 1
        assert result["sid"][1] == 1

    def test_returns_all_rows_when_no_duplicates(self) -> None:
        """Test that all rows are returned when no duplicates exist."""
        # Arrange
        df = pl.DataFrame(
            {
                "sid": [1, 2, 3],
                "close": [10.0, 11.0, 12.0],
            }
        )
        issue = DQIssue(
            level=DQLevel.L1_TECHNICAL,
            severity=DQSeverity.ERROR,
            rule_name="unique",
            message="No duplicates",
            affected_rows=0,
        )

        # Act
        result = filter_failed_rows(df, issue)

        # Assert
        assert len(result) == 3


class TestFilterFailedRowsForeignKey:
    """Tests for foreign_key rule filtering."""

    def test_returns_all_rows_for_manual_review(self) -> None:
        """Test that all rows are returned for manual review."""
        # Arrange
        df = pl.DataFrame(
            {
                "sid": [1, 2, 3],
                "close": [10.0, 11.0, 12.0],
            }
        )
        issue = DQIssue(
            level=DQLevel.L1_TECHNICAL,
            severity=DQSeverity.ERROR,
            rule_name="foreign_key",
            message="Invalid foreign key",
            affected_rows=1,
        )

        # Act
        result = filter_failed_rows(df, issue)

        # Assert
        assert len(result) == 3
        assert result.equals(df)


class TestFilterFailedRowsTypeCheck:
    """Tests for type_check rule filtering."""

    def test_returns_all_rows_for_manual_review(self) -> None:
        """Test that all rows are returned for manual review."""
        # Arrange
        df = pl.DataFrame(
            {
                "sid": [1, 2, 3],
                "close": [10.0, 11.0, 12.0],
            }
        )
        issue = DQIssue(
            level=DQLevel.L2_BUSINESS,
            severity=DQSeverity.WARNING,
            rule_name="type_check",
            message="Type mismatch",
            affected_rows=1,
        )

        # Act
        result = filter_failed_rows(df, issue)

        # Assert
        assert len(result) == 3
        assert result.equals(df)


class TestFilterFailedRowsUnknownRule:
    """Tests for unknown rule types."""

    def test_returns_all_rows_for_unknown_rule(self) -> None:
        """Test that all rows are returned for unknown rule types."""
        # Arrange
        df = pl.DataFrame(
            {
                "sid": [1, 2, 3],
                "close": [10.0, 11.0, 12.0],
            }
        )
        issue = DQIssue(
            level=DQLevel.L1_TECHNICAL,
            severity=DQSeverity.ERROR,
            rule_name="unknown_rule",
            message="Unknown rule",
            affected_rows=1,
        )

        # Act
        result = filter_failed_rows(df, issue)

        # Assert
        assert len(result) == 3
        assert result.equals(df)


class TestFilterFailedRowsEdgeCases:
    """Tests for edge cases."""

    def test_empty_dataframe(self) -> None:
        """Test handling of empty DataFrame."""
        # Arrange
        df = pl.DataFrame(
            {
                "sid": [],
                "close": [],
            }
        )
        issue = DQIssue(
            level=DQLevel.L1_TECHNICAL,
            severity=DQSeverity.ERROR,
            rule_name="not_null",
            message="close has null values",
            affected_rows=0,
        )

        # Act
        result = filter_failed_rows(df, issue)

        # Assert
        assert result.is_empty()

    def test_all_null_values(self) -> None:
        """Test when all values in column are null."""
        # Arrange
        df = pl.DataFrame(
            {
                "sid": [1, 2, 3],
                "close": [None, None, None],
            }
        )
        issue = DQIssue(
            level=DQLevel.L1_TECHNICAL,
            severity=DQSeverity.ERROR,
            rule_name="not_null",
            message="close has null values",
            affected_rows=3,
        )

        # Act
        result = filter_failed_rows(df, issue)

        # Assert
        assert len(result) == 3
