"""Tests for RetryManager."""

import pytest
from ditto_datahub import DataHub
from ditto_foundation.observability import Mode, init, reset_for_testing
from ditto_port.models import IngestionResult
from ditto_port.services.ingestion.retry import (
    RetryManager,
    RetryResult,
)


@pytest.fixture(autouse=True)
def setup_observability():
    """初始化可观测性。"""
    reset_for_testing()
    init(mode=Mode.TESTING_WITH_ASSERTIONS, force=True)
    yield
    reset_for_testing()


@pytest.fixture
def mock_coordinator(mocker):
    """创建 Mock IngestionCoordinator。"""
    coordinator = mocker.Mock()
    coordinator.ingest_date = mocker.Mock()
    return coordinator


@pytest.fixture
def mock_hub(mocker):
    """创建 Mock DataHub。"""
    hub = mocker.Mock(spec=DataHub)
    hub.ingestion_log = mocker.Mock()
    hub.ingestion_log.get_failed_dates = mocker.Mock()
    return hub


@pytest.fixture
def retry_manager(mock_coordinator, mock_hub):
    """创建 RetryManager 实例。"""
    return RetryManager(
        coordinator=mock_coordinator,
        hub=mock_hub,
        source="tushare",
    )


@pytest.mark.unit
class TestRetryResult:
    """测试 RetryResult 类。"""

    def test_create_retry_result(self) -> None:
        """创建重试结果。"""
        results = (
            IngestionResult(
                dataset="stock_daily",
                trade_date="2024-12-25",
                status="success",
                row_count=1000,
            ),
            IngestionResult(
                dataset="stock_daily",
                trade_date="2024-12-26",
                status="failed",
                error="FETCH_ERROR",
                message="获取数据失败",
            ),
            IngestionResult(
                dataset="stock_daily",
                trade_date="2024-12-27",
                status="success",
                row_count=1000,
            ),
        )

        result = RetryResult(
            dataset="stock_daily",
            total_failed=3,
            retried_count=3,
            success_count=2,
            still_failed_count=1,
            results=results,
        )

        assert result.dataset == "stock_daily"
        assert result.total_failed == 3
        assert result.retried_count == 3
        assert result.success_count == 2
        assert result.still_failed_count == 1
        assert len(result.results) == 3


@pytest.mark.unit
class TestGetFailedDates:
    """测试 get_failed_dates 方法。"""

    def test_get_failed_dates_returns_failed_dates(
        self, retry_manager, mock_hub
    ) -> None:
        """返回失败的交易日列表。"""
        # Arrange
        mock_hub.ingestion_log.get_failed_dates.return_value = [
            "2024-12-25",
            "2024-12-26",
            "2024-12-27",
        ]

        # Act
        dates = retry_manager.get_failed_dates(
            dataset="stock_daily",
            max_attempts=3,
        )

        # Assert
        assert dates == ["2024-12-25", "2024-12-26", "2024-12-27"]
        mock_hub.ingestion_log.get_failed_dates.assert_called_once_with(
            dataset="stock_daily", source="tushare", limit=10, max_attempts=3
        )

    def test_get_failed_dates_with_custom_limit(self, retry_manager, mock_hub) -> None:
        """使用自定义限制获取失败日期。"""
        # Arrange
        mock_hub.ingestion_log.get_failed_dates.return_value = [
            "2024-12-25",
            "2024-12-26",
        ]

        # Act
        dates = retry_manager.get_failed_dates(
            dataset="stock_daily",
            max_attempts=3,
            limit=2,
        )

        # Assert
        assert dates == ["2024-12-25", "2024-12-26"]
        mock_hub.ingestion_log.get_failed_dates.assert_called_once_with(
            dataset="stock_daily", source="tushare", limit=2, max_attempts=3
        )

    def test_get_failed_dates_empty(self, retry_manager, mock_hub) -> None:
        """没有失败日期时返回空列表。"""
        # Arrange
        mock_hub.ingestion_log.get_failed_dates.return_value = []

        # Act
        dates = retry_manager.get_failed_dates(dataset="stock_daily")

        # Assert
        assert dates == []

    def test_get_failed_dates_filters_by_attempts(
        self, retry_manager, mock_hub
    ) -> None:
        """按最大尝试次数筛选失败日期。"""
        # Arrange
        mock_hub.ingestion_log.get_failed_dates.return_value = [
            "2024-12-25",
        ]

        # Act
        dates = retry_manager.get_failed_dates(
            dataset="stock_daily",
            max_attempts=2,
        )

        # Assert
        assert dates == ["2024-12-25"]
        mock_hub.ingestion_log.get_failed_dates.assert_called_once_with(
            dataset="stock_daily", source="tushare", limit=10, max_attempts=2
        )


@pytest.mark.unit
class TestRetryFailed:
    """测试 retry_failed 方法。"""

    def test_retry_failed_all_success(
        self, retry_manager, mock_coordinator, mock_hub
    ) -> None:
        """重试失败任务，全部成功。"""
        # Arrange
        mock_hub.ingestion_log.get_failed_dates.return_value = [
            "2024-12-25",
            "2024-12-26",
            "2024-12-27",
        ]

        mock_coordinator.ingest_date.side_effect = [
            IngestionResult(
                dataset="stock_daily",
                trade_date="2024-12-25",
                status="success",
                row_count=1000,
            ),
            IngestionResult(
                dataset="stock_daily",
                trade_date="2024-12-26",
                status="success",
                row_count=1000,
            ),
            IngestionResult(
                dataset="stock_daily",
                trade_date="2024-12-27",
                status="success",
                row_count=1000,
            ),
        ]

        # Act
        result = retry_manager.retry_failed(dataset="stock_daily")

        # Assert
        assert result.dataset == "stock_daily"
        assert result.total_failed == 3
        assert result.retried_count == 3
        assert result.success_count == 3
        assert result.still_failed_count == 0
        assert len(result.results) == 3
        mock_coordinator.ingest_date.assert_called()

    def test_retry_failed_partial_success(
        self, retry_manager, mock_coordinator, mock_hub
    ) -> None:
        """重试失败任务，部分成功。"""
        # Arrange
        mock_hub.ingestion_log.get_failed_dates.return_value = [
            "2024-12-25",
            "2024-12-26",
            "2024-12-27",
        ]

        mock_coordinator.ingest_date.side_effect = [
            IngestionResult(
                dataset="stock_daily",
                trade_date="2024-12-25",
                status="success",
                row_count=1000,
            ),
            IngestionResult(
                dataset="stock_daily",
                trade_date="2024-12-26",
                status="failed",
                error="FETCH_ERROR",
                message="获取数据失败",
            ),
            IngestionResult(
                dataset="stock_daily",
                trade_date="2024-12-27",
                status="success",
                row_count=1000,
            ),
        ]

        # Act
        result = retry_manager.retry_failed(dataset="stock_daily")

        # Assert
        assert result.total_failed == 3
        assert result.retried_count == 3
        assert result.success_count == 2
        assert result.still_failed_count == 1

    def test_retry_failed_with_limit(
        self, retry_manager, mock_coordinator, mock_hub
    ) -> None:
        """使用限制参数重试部分失败任务。"""
        # Arrange
        mock_hub.ingestion_log.get_failed_dates.return_value = [
            "2024-12-25",
            "2024-12-26",
        ]

        mock_coordinator.ingest_date.side_effect = [
            IngestionResult(
                dataset="stock_daily",
                trade_date="2024-12-25",
                status="success",
                row_count=1000,
            ),
            IngestionResult(
                dataset="stock_daily",
                trade_date="2024-12-26",
                status="success",
                row_count=1000,
            ),
        ]

        # Act
        result = retry_manager.retry_failed(
            dataset="stock_daily",
            limit=2,
        )

        # Assert
        assert result.total_failed == 2  # 有3个失败，但只返回2个
        assert result.retried_count == 2
        assert result.success_count == 2

    def test_retry_failed_no_failed_dates(self, retry_manager, mock_hub) -> None:
        """没有失败日期时返回空结果。"""
        # Arrange
        mock_hub.ingestion_log.get_failed_dates.return_value = []

        # Act
        result = retry_manager.retry_failed(dataset="stock_daily")

        # Assert
        assert result.dataset == "stock_daily"
        assert result.total_failed == 0
        assert result.retried_count == 0
        assert result.success_count == 0
        assert result.still_failed_count == 0
        assert len(result.results) == 0

    def test_retry_failed_uses_force_true(
        self, retry_manager, mock_coordinator, mock_hub
    ) -> None:
        """重试时使用 force=True 强制重新摄取。"""
        # Arrange
        mock_hub.ingestion_log.get_failed_dates.return_value = [
            "2024-12-25",
        ]

        mock_coordinator.ingest_date.return_value = IngestionResult(
            dataset="stock_daily",
            trade_date="2024-12-25",
            status="success",
            row_count=1000,
        )

        # Act
        retry_manager.retry_failed(dataset="stock_daily")

        # Assert
        mock_coordinator.ingest_date.assert_called_once_with(
            dataset="stock_daily", trade_date="2024-12-25", force=True
        )

    def test_retry_failed_filters_by_max_attempts(
        self, retry_manager, mock_coordinator, mock_hub
    ) -> None:
        """按最大尝试次数筛选失败任务。"""
        # Arrange
        mock_hub.ingestion_log.get_failed_dates.return_value = [
            "2024-12-25",
        ]

        mock_coordinator.ingest_date.return_value = IngestionResult(
            dataset="stock_daily",
            trade_date="2024-12-25",
            status="success",
            row_count=1000,
        )

        # Act
        retry_manager.retry_failed(
            dataset="stock_daily",
            max_attempts=2,
        )

        # Assert
        mock_hub.ingestion_log.get_failed_dates.assert_called_once_with(
            dataset="stock_daily", source="tushare", limit=10, max_attempts=2
        )

    def test_retry_failed_all_still_failed(
        self, retry_manager, mock_coordinator, mock_hub
    ) -> None:
        """重试全部仍然失败。"""
        # Arrange
        mock_hub.ingestion_log.get_failed_dates.return_value = [
            "2024-12-25",
            "2024-12-26",
        ]

        mock_coordinator.ingest_date.side_effect = [
            IngestionResult(
                dataset="stock_daily",
                trade_date="2024-12-25",
                status="failed",
                error="FETCH_ERROR",
                message="获取数据失败",
            ),
            IngestionResult(
                dataset="stock_daily",
                trade_date="2024-12-26",
                status="failed",
                error="EMPTY_DATA",
                message="数据为空",
            ),
        ]

        # Act
        result = retry_manager.retry_failed(dataset="stock_daily")

        # Assert
        assert result.total_failed == 2
        assert result.retried_count == 2
        assert result.success_count == 0
        assert result.still_failed_count == 2
