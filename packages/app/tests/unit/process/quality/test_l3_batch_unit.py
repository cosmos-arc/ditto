"""L3 Batch Service 返回契约测试."""

from unittest.mock import MagicMock

import pytest
from ditto_app.process.quality import L3BatchService
from ditto_kernel.quality import DQIssue, DQLevel, DQResult, DQSeverity


@pytest.mark.unit
class TestL3BatchServiceContract:
    """L3BatchService 返回契约测试."""

    def test_check_dataset_returns_issues_field(
        self,
        mock_statistical_engine: MagicMock,
        mock_market_service: MagicMock,
        mock_metadata_service: MagicMock,
    ) -> None:
        """check_dataset 返回必须包含 issues 字段."""
        service = L3BatchService(
            engine=mock_statistical_engine,
            market_facade=mock_market_service,
            metadata_facade=mock_metadata_service,
        )

        result = service.check_dataset(
            dataset="stock_daily",
            trade_date="2024-01-15",
        )

        assert "issues" in result
        assert isinstance(result["issues"], list)

    def test_check_dataset_returns_actual_issues(
        self,
        mock_statistical_engine: MagicMock,
        mock_market_service: MagicMock,
        mock_metadata_service: MagicMock,
    ) -> None:
        """check_dataset 返回实际的 issues 列表."""
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

        service = L3BatchService(
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
        assert "issues" in result
        assert len(result["issues"]) == 1
        assert result["issues"][0].rule_name == "zscore_outlier"
