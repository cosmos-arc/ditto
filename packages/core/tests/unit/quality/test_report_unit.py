"""Tests for DQ report generator."""

from ditto_core.quality import DQReportGenerator
from ditto_core.quality.spec import DQIssue, DQLevel, DQResult, DQSeverity


class TestDQReportGenerator:
    """Test cases for DQReportGenerator."""

    def setup_method(self) -> None:
        """Set up test environment."""
        self.generator = DQReportGenerator()

    def test_generate_markdown_report_passed(self) -> None:
        """Test generating markdown report for passed result."""
        result = DQResult(
            dataset="test_dataset",
            passed=True,
            issues=[],
        )

        report = self.generator.generate_markdown_report(result)

        assert "# 数据质量检查报告" in report
        assert "test_dataset" in report
        assert "✅ 通过" in report
        assert "无问题 ✅" in report

    def test_generate_markdown_report_with_issues(self) -> None:
        """Test generating markdown report with issues."""
        issues = [
            DQIssue(
                level=DQLevel.TECHNICAL,
                severity=DQSeverity.ERROR,
                rule_name="not_null",
                message="SID is null",
                affected_rows=5,
            ),
            DQIssue(
                level=DQLevel.BUSINESS,
                severity=DQSeverity.WARNING,
                rule_name="positive",
                message="Negative price",
                affected_rows=2,
            ),
        ]

        result = DQResult(
            dataset="test_dataset",
            passed=False,
            issues=issues,
        )

        report = self.generator.generate_markdown_report(result)

        assert "❌ 失败" in report
        assert "not_null" in report
        assert "positive" in report
        assert "ERROR | 1" in report
        assert "WARNING | 1" in report

    def test_generate_html_report(self) -> None:
        """Test generating HTML report."""
        issues = [
            DQIssue(
                level=DQLevel.TECHNICAL,
                severity=DQSeverity.ERROR,
                rule_name="unique",
                message="Duplicate key",
                affected_rows=1,
            )
        ]

        result = DQResult(
            dataset="test_dataset",
            passed=False,
            issues=issues,
        )

        html = self.generator.generate_html_report(result)

        assert "<!DOCTYPE html>" in html
        assert "test_dataset" in html
        assert "unique" in html
        assert "Duplicate key" in html

    def test_generate_batch_summary(self) -> None:
        """Test generating batch summary."""
        results = {
            "dataset_a": DQResult(dataset="dataset_a", passed=True, issues=[]),
            "dataset_b": DQResult(
                dataset="dataset_b",
                passed=False,
                issues=[
                    DQIssue(
                        level=DQLevel.BUSINESS,
                        severity=DQSeverity.WARNING,
                        rule_name="test_rule",
                        message="Test message",
                        affected_rows=1,
                    )
                ],
            ),
        }

        summary = self.generator.generate_batch_summary(
            results=results,
            trade_date="2024-01-01",
        )

        assert "# DQ 批量检查摘要" in summary
        assert "2024-01-01" in summary
        assert "dataset_a" in summary
        assert "dataset_b" in summary
        assert "检查数据集: 2" in summary
