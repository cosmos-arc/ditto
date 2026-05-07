"""QualityPatrolService 返回契约测试."""

from unittest.mock import MagicMock

import pytest
from ditto_application.processes.quality import QualityPatrolService
from ditto_application.processes.quality.types import L3CheckResult
from ditto_kernel.quality import DQIssue, DQLevel, DQResult, DQSeverity


@pytest.mark.unit
class TestQualityPatrolServiceContract:
    """QualityPatrolService 返回契约测试."""

    def test_check_dataset_returns_l3_check_result(
        self,
        mock_statistical_engine: MagicMock,
        mock_market_service: MagicMock,
        mock_metadata_service: MagicMock,
    ) -> None:
        """check_dataset 返回 L3CheckResult 实例."""
        service = QualityPatrolService(
            engine=mock_statistical_engine,
            market_facade=mock_market_service,
            metadata_facade=mock_metadata_service,
        )

        result = service.check_dataset(
            dataset="stock_daily",
            trade_date="2024-01-15",
        )

        assert isinstance(result, L3CheckResult)
        assert result.passed is True
        assert result.issue_count == 0

    def test_check_dataset_returns_actual_issues(
        self,
        mock_statistical_engine: MagicMock,
        mock_market_service: MagicMock,
        mock_metadata_service: MagicMock,
    ) -> None:
        """check_dataset 返回包含 issues 的 L3CheckResult."""
        # Arrange
        sample_issue = DQIssue(
            level=DQLevel.STATISTICAL,
            severity=DQSeverity.ALERT,
            rule_name="zscore_outlier",
            message="Volume zscore exceeds threshold",
            affected_rows=5,
            sample_data=[{"instrument_id": 1000001, "trade_date": "2024-01-15"}],
        )
        mock_statistical_engine.check_statistical.return_value = DQResult(
            dataset="stock_daily",
            passed=True,
            issues=[sample_issue],
        )

        service = QualityPatrolService(
            engine=mock_statistical_engine,
            market_facade=mock_market_service,
            metadata_facade=mock_metadata_service,
        )

        # Act
        result = service.check_dataset(
            dataset="stock_daily",
            trade_date="2024-01-15",
        )

        # Assert
        assert isinstance(result, L3CheckResult)
        assert result.issue_count == 1
        assert result.issues[0].rule_name == "zscore_outlier"

    def test_check_dataset_error_returns_l3_check_result(
        self,
        mock_statistical_engine: MagicMock,
        mock_market_service: MagicMock,
        mock_metadata_service: MagicMock,
    ) -> None:
        """check_dataset 异常时返回 L3CheckResult（has_error=True）."""
        mock_statistical_engine.check_statistical.side_effect = RuntimeError("boom")

        service = QualityPatrolService(
            engine=mock_statistical_engine,
            market_facade=mock_market_service,
            metadata_facade=mock_metadata_service,
        )

        result = service.check_dataset(
            dataset="stock_daily",
            trade_date="2024-01-15",
        )

        assert isinstance(result, L3CheckResult)
        assert result.has_error is True
        assert result.passed is False
        assert "RuntimeError" in result.error
