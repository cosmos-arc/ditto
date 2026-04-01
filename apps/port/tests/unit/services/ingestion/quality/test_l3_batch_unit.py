"""L3 Batch Service 返回契约测试."""

from unittest.mock import MagicMock

import polars as pl
import pytest
from ditto_data.quality.severity import DQSeverity
from ditto_data.quality.spec import DQIssue, DQLevel, DQResult
from ditto_port.services.ingestion.quality.l3_batch_service import L3BatchService


@pytest.fixture
def mock_engine() -> MagicMock:
    """创建 mock DQ 引擎."""
    engine = MagicMock()
    result = DQResult(
        dataset="stock_daily",
        passed=True,
        issues=[],
    )
    engine.check_statistical.return_value = result
    return engine


@pytest.fixture
def mock_market_service() -> MagicMock:
    """创建 mock MarketService."""
    service = MagicMock()
    service.find_bars.return_value = pl.DataFrame()
    return service


@pytest.fixture
def mock_metadata_service() -> MagicMock:
    """创建 mock MetadataService."""
    service = MagicMock()
    service.list_calendar_range.return_value = pl.DataFrame()
    return service


@pytest.mark.unit
class TestL3BatchServiceContract:
    """L3BatchService 返回契约测试."""

    def test_check_dataset_returns_issues_field(
        self,
        mock_engine: MagicMock,
        mock_market_service: MagicMock,
        mock_metadata_service: MagicMock,
    ) -> None:
        """check_dataset 返回必须包含 issues 字段."""
        service = L3BatchService(
            engine=mock_engine,
            market_service=mock_market_service,
            metadata_service=mock_metadata_service,
        )

        result = service.check_dataset(
            dataset="stock_daily",
            trade_date="2024-01-15",
        )

        assert "issues" in result
        assert isinstance(result["issues"], list)

    def test_check_dataset_returns_actual_issues(
        self,
        mock_engine: MagicMock,
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
        mock_engine.check_statistical.return_value = DQResult(
            dataset="stock_daily",
            passed=True,
            issues=[sample_issue],
        )

        service = L3BatchService(
            engine=mock_engine,
            market_service=mock_market_service,
            metadata_service=mock_metadata_service,
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
