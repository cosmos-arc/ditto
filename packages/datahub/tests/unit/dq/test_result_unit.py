"""Tests for DQ result models."""

from ditto_datahub.models import DQIssue, DQLevel, DQResult, DQSeverity


class TestDQLevel:
    """Test DQLevel enum."""

    def test_level_values(self) -> None:
        """Test level enum values."""
        assert DQLevel.L1_TECHNICAL.value == "l1_technical"
        assert DQLevel.L2_BUSINESS.value == "l2_business"
        assert DQLevel.L3_STATISTICAL.value == "l3_statistical"


class TestDQSeverity:
    """Test DQSeverity enum."""

    def test_severity_values(self) -> None:
        """Test severity enum values."""
        assert DQSeverity.ERROR.value == "error"
        assert DQSeverity.WARNING.value == "warning"
        assert DQSeverity.ALERT.value == "alert"


class TestDQIssue:
    """Test DQIssue dataclass."""

    def test_create_issue(self) -> None:
        """Test creating a DQ issue."""
        issue = DQIssue(
            level=DQLevel.L1_TECHNICAL,
            severity=DQSeverity.ERROR,
            rule_name="primary_key_unique",
            message="Found 2 duplicate (sid, trade_date)",
            affected_rows=2,
            sample_data=[{"sid": 100001, "trade_date": "2024-01-01"}],
        )

        assert issue.level == DQLevel.L1_TECHNICAL
        assert issue.severity == DQSeverity.ERROR
        assert issue.rule_name == "primary_key_unique"
        assert issue.affected_rows == 2
        assert len(issue.sample_data) == 1

    def test_create_issue_minimal(self) -> None:
        """Test creating issue with minimal required fields."""
        issue = DQIssue(
            level=DQLevel.L2_BUSINESS,
            severity=DQSeverity.WARNING,
            rule_name="ohlc_consistency",
            message="OHLC relationship violated",
        )

        assert issue.affected_rows == 0
        assert issue.sample_data == []


class TestDQResult:
    """Test DQResult dataclass."""

    def test_create_result(self) -> None:
        """Test creating a DQ result."""
        issues = [
            DQIssue(
                level=DQLevel.L1_TECHNICAL,
                severity=DQSeverity.ERROR,
                rule_name="primary_key_unique",
                message="Duplicate key",
                affected_rows=2,
            ),
            DQIssue(
                level=DQLevel.L2_BUSINESS,
                severity=DQSeverity.WARNING,
                rule_name="ohlc_consistency",
                message="OHLC violated",
                affected_rows=1,
            ),
        ]

        result = DQResult(
            dataset="etf_daily",
            passed=False,
            issues=issues,
        )

        assert result.dataset == "etf_daily"
        assert result.passed is False
        assert len(result.issues) == 2

    def test_has_errors_property(self) -> None:
        """Test has_errors property."""
        # With ERROR issues
        result_with_errors = DQResult(
            dataset="etf_daily",
            passed=False,
            issues=[
                DQIssue(
                    level=DQLevel.L1_TECHNICAL,
                    severity=DQSeverity.ERROR,
                    rule_name="pk_unique",
                    message="Duplicate",
                ),
                DQIssue(
                    level=DQLevel.L2_BUSINESS,
                    severity=DQSeverity.WARNING,
                    rule_name="ohlc",
                    message="OHLC violated",
                ),
            ],
        )
        assert result_with_errors.has_errors is True
        assert result_with_errors.has_warnings is True

        # With only WARNING issues
        result_only_warnings = DQResult(
            dataset="etf_daily",
            passed=True,
            issues=[
                DQIssue(
                    level=DQLevel.L2_BUSINESS,
                    severity=DQSeverity.WARNING,
                    rule_name="ohlc",
                    message="OHLC violated",
                ),
            ],
        )
        assert result_only_warnings.has_errors is False
        assert result_only_warnings.has_warnings is True

        # With no issues
        result_clean = DQResult(
            dataset="etf_daily",
            passed=True,
            issues=[],
        )
        assert result_clean.has_errors is False
        assert result_clean.has_warnings is False

    def test_error_count_property(self) -> None:
        """Test error_count calculation."""
        result = DQResult(
            dataset="etf_daily",
            passed=False,
            issues=[
                DQIssue(
                    level=DQLevel.L1_TECHNICAL,
                    severity=DQSeverity.ERROR,
                    rule_name="pk_unique",
                    message="Duplicate",
                ),
                DQIssue(
                    level=DQLevel.L1_TECHNICAL,
                    severity=DQSeverity.ERROR,
                    rule_name="null_check",
                    message="Null value",
                ),
                DQIssue(
                    level=DQLevel.L2_BUSINESS,
                    severity=DQSeverity.WARNING,
                    rule_name="ohlc",
                    message="OHLC violated",
                ),
            ],
        )

        # error_count should only count ERROR severity
        assert result.error_count == 2
        # We'll add warn_count property later
