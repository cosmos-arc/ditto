"""Tests for DQ result models."""

from ditto_kernel.quality import DQIssue, DQLevel, DQResult, DQSeverity


class TestDQLevel:
    """Test DQLevel enum."""

    def test_level_values(self) -> None:
        """Test level enum values."""
        assert DQLevel.TECHNICAL.value == "technical"
        assert DQLevel.BUSINESS.value == "business"
        assert DQLevel.STATISTICAL.value == "statistical"


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
            level=DQLevel.TECHNICAL,
            severity=DQSeverity.ERROR,
            rule_name="primary_key_unique",
            message="Found 2 duplicate (instrument_id, trade_date)",
            affected_rows=2,
            sample_data=[{"instrument_id": 100001, "trade_date": "2024-01-01"}],
        )

        assert issue.level == DQLevel.TECHNICAL
        assert issue.severity == DQSeverity.ERROR
        assert issue.rule_name == "primary_key_unique"
        assert issue.affected_rows == 2
        assert len(issue.sample_data) == 1

    def test_create_issue_minimal(self) -> None:
        """Test creating issue with minimal required fields."""
        issue = DQIssue(
            level=DQLevel.BUSINESS,
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
                level=DQLevel.TECHNICAL,
                severity=DQSeverity.ERROR,
                rule_name="primary_key_unique",
                message="Duplicate key",
                affected_rows=2,
            ),
            DQIssue(
                level=DQLevel.BUSINESS,
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
                    level=DQLevel.TECHNICAL,
                    severity=DQSeverity.ERROR,
                    rule_name="test",
                    message="Test",
                )
            ],
        )

        assert result_with_errors.has_errors is True

        # Without ERROR issues
        result_no_errors = DQResult(
            dataset="etf_daily",
            passed=True,
            issues=[
                DQIssue(
                    level=DQLevel.BUSINESS,
                    severity=DQSeverity.WARNING,
                    rule_name="test",
                    message="Test",
                )
            ],
        )

        assert result_no_errors.has_errors is False

    def test_has_warnings_property(self) -> None:
        """Test has_warnings property."""
        result_with_warnings = DQResult(
            dataset="etf_daily",
            passed=False,
            issues=[
                DQIssue(
                    level=DQLevel.BUSINESS,
                    severity=DQSeverity.WARNING,
                    rule_name="test",
                    message="Test",
                )
            ],
        )

        assert result_with_warnings.has_warnings is True

    def test_alert_count_property(self) -> None:
        """Test alert_count property."""
        result = DQResult(
            dataset="etf_daily",
            passed=False,
            issues=[
                DQIssue(
                    level=DQLevel.STATISTICAL,
                    severity=DQSeverity.ALERT,
                    rule_name="test",
                    message="Test",
                ),
                DQIssue(
                    level=DQLevel.STATISTICAL,
                    severity=DQSeverity.ALERT,
                    rule_name="test2",
                    message="Test2",
                ),
            ],
        )

        assert result.alert_count == 2
