"""Tests for TechnicalChecker."""

import polars as pl
import pytest
from ditto_datahub.dq.checkers.technical import TechnicalChecker
from ditto_datahub.models import DQLevel, DQSeverity


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
            assert issues[0].level == DQLevel.L1_TECHNICAL
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
            assert issues[0].level == DQLevel.L1_TECHNICAL
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

    @pytest.mark.parametrize(
        (
            "data_dict",
            "rules",
            "expected_issue_count",
            "expected_severity",
            "check_message_contains",
        ),
        [
            # Pass case: valid types
            (
                {
                    "sid": [1, 2, 3],
                    "close": [10.0, 20.0, 30.0],
                    "volume": [100, 200, 300],
                },
                [
                    {
                        "rule": "type_check",
                        "types": {
                            "sid": "Int64",
                            "close": "Float64",
                            "volume": "Int64",
                        },
                    }
                ],
                0,
                None,
                None,
            ),
            # Fail case: invalid type (string instead of Float64)
            (
                {"sid": [1, 2, 3], "close": ["10.0", "20.0", "30.0"]},
                [{"rule": "type_check", "types": {"sid": "Int64", "close": "Float64"}}],
                1,
                DQSeverity.ERROR,
                "close",
            ),
        ],
    )
    def test_check_type(
        self,
        data_dict: dict,
        rules: list[dict],
        expected_issue_count: int,
        expected_severity: DQSeverity | None,
        check_message_contains: str | None,
    ) -> None:
        """Test type check with valid and invalid types."""
        df = pl.DataFrame(data_dict)
        issues = self.checker.check(df, rules)

        assert len(issues) == expected_issue_count
        if expected_issue_count > 0:
            assert issues[0].level == DQLevel.L1_TECHNICAL
            assert issues[0].severity == expected_severity
            if check_message_contains:
                assert check_message_contains in issues[0].message

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

    def test_foreign_key_valid(self, mocker) -> None:
        """Test foreign key check with valid references."""
        df = pl.DataFrame(
            {
                "sid": [1, 2, 3],
                "index_sid": [100, 200, 300],
            }
        )

        # Mock hub that returns valid sids
        mock_hub = mocker.MagicMock()
        mock_hub.sql.return_value = pl.DataFrame({"sid": [100, 200, 300, 400]})

        rule = {
            "rule": "foreign_key",
            "column": "index_sid",
            "reference": "security.sid",
        }
        context = {"hub": mock_hub}

        issues = self.checker.check(df, [rule], context)

        assert len(issues) == 0

    def test_foreign_key_invalid(self, mocker) -> None:
        """Test foreign key check with invalid references."""
        df = pl.DataFrame(
            {
                "sid": [1, 2, 3],
                "index_sid": [100, 999, 300],  # 999 is invalid
            }
        )

        mock_hub = mocker.MagicMock()
        mock_hub.sql.return_value = pl.DataFrame({"sid": [100, 200, 300, 400]})

        rule = {
            "rule": "foreign_key",
            "column": "index_sid",
            "reference": "security.sid",
        }
        context = {"hub": mock_hub}

        issues = self.checker.check(df, [rule], context)

        assert len(issues) == 1
        assert issues[0].rule_name == "foreign_key"
        assert issues[0].affected_rows == 1

    def test_foreign_key_no_context(self) -> None:
        """Test foreign key check without hub context (should skip)."""
        df = pl.DataFrame({"index_sid": [100, 200]})
        rule = {
            "rule": "foreign_key",
            "column": "index_sid",
            "reference": "security.sid",
        }

        issues = self.checker.check(df, [rule], context=None)

        assert len(issues) == 0  # Should skip without context

    def test_foreign_key_invalid_dataset_sql_injection(self, mocker) -> None:
        """Test foreign key check with SQL injection in dataset name."""
        df = pl.DataFrame({"index_sid": [100, 200]})
        mock_hub = mocker.MagicMock()

        # SQL injection attempt: dataset name not in whitelist
        rule = {
            "rule": "foreign_key",
            "column": "index_sid",
            "reference": "malicious_table; DROP TABLE security--.sid",
        }
        context = {"hub": mock_hub}

        issues = self.checker.check(df, [rule], context)

        # Should reject due to dataset not in whitelist
        assert len(issues) == 0
        # hub.sql should not be called
        mock_hub.sql.assert_not_called()

    def test_foreign_key_invalid_column_sql_injection(self, mocker) -> None:
        """Test foreign key check with SQL injection in column name."""
        df = pl.DataFrame({"index_sid": [100, 200]})
        mock_hub = mocker.MagicMock()

        # SQL injection attempt: column name with invalid characters
        rule = {
            "rule": "foreign_key",
            "column": "index_sid",
            "reference": "security.sid; DROP TABLE users--",
        }
        context = {"hub": mock_hub}

        issues = self.checker.check(df, [rule], context)

        # Should reject due to invalid column format
        assert len(issues) == 0
        # hub.sql should not be called
        mock_hub.sql.assert_not_called()

    def test_foreign_key_valid_whitelist_dataset(self, mocker) -> None:
        """Test foreign key check with valid whitelisted dataset."""
        df = pl.DataFrame({"sid": [1, 2, 3]})
        mock_hub = mocker.MagicMock()
        mock_hub.sql.return_value = pl.DataFrame({"sid": [1, 2, 3, 4, 5]})

        # Test with all whitelisted datasets
        valid_datasets = [
            "security",
            "security_mapping",
            "trading_calendar",
            "universe",
            "universe_constituent",
            "index_weight",
            "stock_daily",
            "etf_daily",
            "index_daily",
            "adj_factor",
        ]

        for dataset in valid_datasets:
            rule = {
                "rule": "foreign_key",
                "column": "sid",
                "reference": f"{dataset}.sid",
            }
            context = {"hub": mock_hub}

            # Reset mock for each iteration
            mock_hub.sql.reset_mock()

            issues = self.checker.check(df, [rule], context)

            # Should pass whitelist validation and call hub.sql
            assert len(issues) == 0
            mock_hub.sql.assert_called_once()

    def test_check_unique_missing_columns(self) -> None:
        """Test unique check with missing columns."""
        df = pl.DataFrame(
            {
                "sid": [1, 2, 3],
                # trade_date column missing
            }
        )

        rules = [
            {
                "rule": "unique",
                "columns": ["sid", "trade_date"],  # trade_date doesn't exist
                "message": "Primary key unique",
            }
        ]

        issues = self.checker.check(df, rules)

        # Should return None when columns are missing
        assert len(issues) == 0

    def test_check_not_null_multiple_columns_partial_missing(self) -> None:
        """Test not null check with multiple columns where some are missing."""
        df = pl.DataFrame(
            {
                "sid": [1, 2, 3],
                # trade_date column missing
                "value": [10.0, 20.0, 30.0],
            }
        )

        rules = [
            {
                "rule": "not_null",
                "columns": ["sid", "trade_date", "value"],  # trade_date missing
                "message": "Required fields",
            }
        ]

        issues = self.checker.check(df, rules)

        # Should skip missing columns and check existing ones
        assert len(issues) == 0  # All existing columns have no nulls

    def test_check_type_multiple_columns(self) -> None:
        """Test type check with multiple columns."""
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
                "types": {
                    "sid": "Int64",
                    "close": "Float64",
                    "volume": "Int64",
                },
            }
        ]

        issues = self.checker.check(df, rules)

        assert len(issues) == 0

    def test_foreign_key_invalid_reference_format(self, mocker) -> None:
        """Test foreign key check with invalid reference format (no dot)."""
        df = pl.DataFrame({"sid": [1, 2]})
        mock_hub = mocker.MagicMock()

        rule = {
            "rule": "foreign_key",
            "column": "sid",
            "reference": "security",  # No dot separator
        }
        context = {"hub": mock_hub}

        issues = self.checker.check(df, [rule], context)

        # Should return None for invalid reference format
        assert len(issues) == 0
        mock_hub.sql.assert_not_called()

    def test_foreign_key_empty_reference_data(self, mocker) -> None:
        """Test foreign key check with empty reference data."""
        df = pl.DataFrame({"sid": [1, 2, 3]})
        mock_hub = mocker.MagicMock()
        mock_hub.sql.return_value = pl.DataFrame()  # Empty result

        rule = {
            "rule": "foreign_key",
            "column": "sid",
            "reference": "security.sid",
        }
        context = {"hub": mock_hub}

        issues = self.checker.check(df, [rule], context)

        # Should return None when reference data is empty
        assert len(issues) == 0

    def test_foreign_key_column_not_in_dataframe(self, mocker) -> None:
        """Test foreign key check when column not in dataframe."""
        df = pl.DataFrame({"other_column": [1, 2, 3]})  # sid column missing
        mock_hub = mocker.MagicMock()
        mock_hub.sql.return_value = pl.DataFrame({"sid": [1, 2, 3]})

        rule = {
            "rule": "foreign_key",
            "column": "sid",  # Doesn't exist in df
            "reference": "security.sid",
        }
        context = {"hub": mock_hub}

        issues = self.checker.check(df, [rule], context)

        # Should return None when column doesn't exist in df
        assert len(issues) == 0

    def test_foreign_key_exception_handling(self, mocker) -> None:
        """Test foreign key check handles exceptions gracefully."""
        df = pl.DataFrame({"sid": [1, 2, 3]})
        mock_hub = mocker.MagicMock()
        mock_hub.sql.side_effect = Exception("SQL execution failed")

        rule = {
            "rule": "foreign_key",
            "column": "sid",
            "reference": "security.sid",
        }
        context = {"hub": mock_hub}

        issues = self.checker.check(df, [rule], context)

        # Should return None on exception
        assert len(issues) == 0

    def test_check_unknown_rule_type(self) -> None:
        """Test check with unknown rule type."""
        df = pl.DataFrame({"sid": [1, 2, 3]})

        rules = [
            {
                "rule": "unknown_rule",  # Unknown rule type
                "message": "Unknown rule",
            }
        ]

        issues = self.checker.check(df, rules)

        # Should return None for unknown rule types
        assert len(issues) == 0

    def test_check_empty_rules_list(self) -> None:
        """Test check with empty rules list."""
        df = pl.DataFrame({"sid": [1, 2, 3]})

        issues = self.checker.check(df, [])

        assert len(issues) == 0

    def test_check_with_context_parameter(self) -> None:
        """Test check with context parameter (not used by all rules)."""
        df = pl.DataFrame({"sid": [1, 2, 3], "value": [10.0, 20.0, 30.0]})

        rules = [
            {
                "rule": "not_null",
                "columns": ["sid"],
                "message": "SID required",
            }
        ]

        context = {"dataset": "test", "source": "api"}

        issues = self.checker.check(df, rules, context)

        assert len(issues) == 0

    def test_foreign_key_with_null_values(self, mocker) -> None:
        """Test foreign key check with null values in data."""
        df = pl.DataFrame({"sid": [1, None, 3, 999]})
        mock_hub = mocker.MagicMock()
        mock_hub.sql.return_value = pl.DataFrame({"sid": [1, 2, 3, 4, 5]})

        rule = {
            "rule": "foreign_key",
            "column": "sid",
            "reference": "security.sid",
        }
        context = {"hub": mock_hub}

        issues = self.checker.check(df, [rule], context)

        # Should detect invalid reference (999), ignoring nulls
        assert len(issues) == 1
        assert issues[0].rule_name == "foreign_key"
        assert issues[0].affected_rows == 1

    def test_check_unique_with_null_values(self) -> None:
        """Test unique check handles null values correctly."""
        df = pl.DataFrame(
            {
                "sid": [1, 1, 2],
                "trade_date": [None, None, "2024-01-01"],  # Nulls in unique key
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

        # Polars treats nulls as equal, so (1, null) appears twice
        assert len(issues) == 1
        assert issues[0].rule_name == "unique"
