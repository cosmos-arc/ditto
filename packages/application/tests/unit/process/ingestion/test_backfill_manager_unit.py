"""Tests for BackfillManager."""

import pytest
from ditto_application.processes.ingestion.backfill_manager import BackfillManager
from ditto_data.models.ingestion import BackfillResult, IngestionResult
from ditto_platform.foundation import (
    Environment,
    ObservabilityConfig,
    init,
    reset_for_testing,
)


@pytest.fixture(autouse=True)
def setup_observability():
    """初始化可观测性。"""
    reset_for_testing()
    config = ObservabilityConfig(
        environment=Environment.TESTING,
        pytest_running=True,
        assertions_enabled=True,
        verbose_logging=False,
        tracing_enabled=True,
        tracing_sample_rate=1.0,
        metrics_enabled=True,
    )
    init(config, force=True)
    yield
    reset_for_testing()


@pytest.fixture
def mock_coordinator(mocker):
    """创建 Mock IngestionCoordinator。"""
    coordinator = mocker.Mock()
    coordinator.ingest_date = mocker.Mock()
    return coordinator


@pytest.fixture
def mock_metadata_service(mocker):
    """创建 Mock MetadataService。"""
    service = mocker.Mock()
    service.list_trading_days = mocker.Mock(return_value=[])
    service.calendar.get_first_trading_day = mocker.Mock(return_value="2020-01-02")
    service.get_last_trading_day = mocker.Mock(return_value="2024-12-31")
    return service


@pytest.fixture
def mock_ingestion_log_store(mocker):
    """创建 Mock IngestionLogStore。"""
    service = mocker.Mock()
    service.list_ingested_dates = mocker.Mock(return_value=[])
    return service


@pytest.fixture
def backfill_manager(mock_coordinator, mock_metadata_service, mock_ingestion_log_store):
    """创建 BackfillManager 实例。"""
    return BackfillManager(
        coordinator=mock_coordinator,
        metadata_service=mock_metadata_service,
        ingestion_log_store=mock_ingestion_log_store,
    )


@pytest.mark.unit
class TestBackfillResult:
    """测试 BackfillResult 类。"""

    def test_create_backfill_result(self) -> None:
        """创建回补结果。"""
        results = [
            IngestionResult(
                dataset="stock_daily",
                trade_date="2024-12-25",
                status="success",
                row_count=1000,
            ),
            IngestionResult(
                dataset="stock_daily",
                trade_date="2024-12-26",
                status="skipped",
                message="数据已存在",
            ),
            IngestionResult(
                dataset="stock_daily",
                trade_date="2024-12-27",
                status="failed",
                error="FETCH_ERROR",
                message="获取数据失败",
            ),
        ]

        result = BackfillResult(
            dataset="stock_daily",
            total_dates=3,
            success_count=1,
            skipped_count=1,
            failed_count=1,
            results=results,
        )

        assert result.dataset == "stock_daily"
        assert result.total_dates == 3
        assert result.success_count == 1
        assert result.skipped_count == 1
        assert result.failed_count == 1
        assert len(result.results) == 3


@pytest.mark.unit
class TestBackfillRange:
    """测试 backfill_range 方法。"""

    def test_backfill_range_success_all_dates(
        self,
        backfill_manager,
        mock_coordinator,
        mock_metadata_service,
    ) -> None:
        """成功回补日期范围内的所有交易日。"""
        # Arrange
        mock_metadata_service.list_trading_days.return_value = [
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
        result = backfill_manager.backfill_range(
            dataset="stock_daily",
            start_date="2024-12-25",
            end_date="2024-12-27",
        )

        # Assert
        assert result.dataset == "stock_daily"
        assert result.total_dates == 3
        assert result.success_count == 3
        assert result.skipped_count == 0
        assert result.failed_count == 0
        assert len(result.results) == 3
        mock_coordinator.ingest_date.assert_called()

    def test_backfill_range_with_skipped_dates(
        self,
        backfill_manager,
        mock_coordinator,
        mock_metadata_service,
    ) -> None:
        """日期范围内有跳过的日期。"""
        # Arrange
        mock_metadata_service.list_trading_days.return_value = [
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
                status="skipped",
                message="数据已存在",
            ),
            IngestionResult(
                dataset="stock_daily",
                trade_date="2024-12-27",
                status="success",
                row_count=1000,
            ),
        ]

        # Act
        result = backfill_manager.backfill_range(
            dataset="stock_daily",
            start_date="2024-12-25",
            end_date="2024-12-27",
        )

        # Assert
        assert result.total_dates == 3
        assert result.success_count == 2
        assert result.skipped_count == 1
        assert result.failed_count == 0

    def test_backfill_range_with_failed_dates(
        self,
        backfill_manager,
        mock_coordinator,
        mock_metadata_service,
    ) -> None:
        """日期范围内有失败的日期。"""
        # Arrange
        mock_metadata_service.list_trading_days.return_value = [
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
        result = backfill_manager.backfill_range(
            dataset="stock_daily",
            start_date="2024-12-25",
            end_date="2024-12-27",
        )

        # Assert
        assert result.total_dates == 3
        assert result.success_count == 2
        assert result.skipped_count == 0
        assert result.failed_count == 1

    def test_backfill_range_empty_range(
        self, backfill_manager, mock_metadata_service
    ) -> None:
        """日期范围为空时返回空结果。"""
        # Arrange
        mock_metadata_service.list_trading_days.return_value = []

        # Act
        result = backfill_manager.backfill_range(
            dataset="stock_daily",
            start_date="2024-12-25",
            end_date="2024-12-27",
        )

        # Assert
        assert result.total_dates == 0
        assert result.success_count == 0
        assert result.skipped_count == 0
        assert result.failed_count == 0
        assert len(result.results) == 0

    def test_backfill_range_parallel_execution(
        self,
        backfill_manager,
        mock_coordinator,
        mock_metadata_service,
    ) -> None:
        """并行执行回补任务。"""
        # Arrange
        mock_metadata_service.list_trading_days.return_value = [
            "2024-12-25",
            "2024-12-26",
            "2024-12-27",
        ]

        mock_coordinator.ingest_date.side_effect = [
            IngestionResult(
                dataset="stock_daily",
                trade_date=date,
                status="success",
                row_count=1000,
            )
            for date in ["2024-12-25", "2024-12-26", "2024-12-27"]
        ]

        # Act
        result = backfill_manager.backfill_range(
            dataset="stock_daily",
            start_date="2024-12-25",
            end_date="2024-12-27",
            parallel=3,
        )

        # Assert
        assert result.total_dates == 3
        assert result.success_count == 3
        assert mock_coordinator.ingest_date.call_count == 3


@pytest.mark.unit
class TestBackfillMissing:
    """测试 backfill_missing 方法。"""

    def test_backfill_missing_finds_missing_dates(
        self,
        backfill_manager,
        mock_coordinator,
        mock_metadata_service,
        mock_ingestion_log_store,
    ) -> None:
        """查找并回补缺失的日期。"""
        # Arrange
        # 交易日历有5个交易日
        mock_metadata_service.list_trading_days.return_value = [
            "2024-12-23",
            "2024-12-24",
            "2024-12-25",
            "2024-12-26",
            "2024-12-27",
        ]

        # 已摄取3个日期
        mock_ingestion_log_store.list_ingested_dates.return_value = [
            "2024-12-23",
            "2024-12-25",
            "2024-12-27",
        ]

        mock_coordinator.ingest_date.side_effect = [
            IngestionResult(
                dataset="stock_daily",
                trade_date="2024-12-24",
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
        result = backfill_manager.backfill_missing(dataset="stock_daily")

        # Assert
        # 应该只回补缺失的2个日期
        assert result.total_dates == 2
        assert result.success_count == 2
        assert mock_coordinator.ingest_date.call_count == 2

    def test_backfill_missing_no_missing_dates(
        self, backfill_manager, mock_metadata_service, mock_ingestion_log_store
    ) -> None:
        """没有缺失日期时返回空结果。"""
        # Arrange
        mock_metadata_service.list_trading_days.return_value = [
            "2024-12-25",
            "2024-12-26",
            "2024-12-27",
        ]

        mock_ingestion_log_store.list_ingested_dates.return_value = [
            "2024-12-25",
            "2024-12-26",
            "2024-12-27",
        ]

        # Act
        result = backfill_manager.backfill_missing(dataset="stock_daily")

        # Assert
        assert result.total_dates == 0
        assert result.success_count == 0
        assert result.skipped_count == 0
        assert result.failed_count == 0

    def test_backfill_missing_uses_calendar_range(
        self,
        backfill_manager,
        mock_coordinator,
        mock_metadata_service,
        mock_ingestion_log_store,
    ) -> None:
        """使用日历的完整日期范围查找缺失。"""
        # Arrange
        mock_metadata_service.calendar.get_first_trading_day.return_value = "2024-12-01"
        mock_metadata_service.get_last_trading_day.return_value = "2024-12-31"

        # 模拟 get_range 调用
        def get_range_side_effect(start, end):
            if start == "2024-12-01" and end == "2024-12-31":
                return ["2024-12-25", "2024-12-26", "2024-12-27"]
            return []

        mock_metadata_service.list_trading_days.side_effect = get_range_side_effect

        mock_ingestion_log_store.list_ingested_dates.return_value = ["2024-12-25"]

        mock_coordinator.ingest_date.side_effect = [
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
        result = backfill_manager.backfill_missing(dataset="stock_daily")

        # Assert
        assert result.total_dates == 2
        mock_metadata_service.list_trading_days.assert_called_once_with(
            "2024-12-01", "2024-12-31"
        )

    def test_backfill_missing_with_source(
        self,
        backfill_manager,
        mock_coordinator,
        mock_metadata_service,
        mock_ingestion_log_store,
    ) -> None:
        """测试 backfill_missing 支持 source 参数。"""
        # Arrange
        mock_metadata_service.list_trading_days.return_value = [
            "2024-12-25",
            "2024-12-26",
            "2024-12-27",
        ]

        # 验证 source 参数被正确传递
        mock_ingestion_log_store.list_ingested_dates.return_value = ["2024-12-25"]

        mock_coordinator.ingest_date.side_effect = [
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
        result = backfill_manager.backfill_missing(
            dataset="stock_daily",
            source="tushare",
        )

        # Assert
        assert result.total_dates >= 0
        # 验证 source 参数被正确传递给 list_ingested_dates
        mock_ingestion_log_store.list_ingested_dates.assert_called_once_with(
            "stock_daily", "tushare"
        )

    def test_backfill_range_year_level_parallel(
        self, backfill_manager, mock_coordinator, mock_metadata_service
    ) -> None:
        """测试年份级并行策略。"""
        # Arrange - 准备跨年数据
        mock_metadata_service.list_trading_days.return_value = [
            "2023-12-29",
            "2023-12-30",
            "2024-01-02",
            "2024-01-03",
        ]

        mock_coordinator.ingest_date.side_effect = [
            IngestionResult(
                dataset="stock_daily",
                trade_date=date,
                status="success",
                row_count=1000,
            )
            for date in ["2023-12-29", "2023-12-30", "2024-01-02", "2024-01-03"]
        ]

        # Act
        result = backfill_manager.backfill_range(
            dataset="stock_daily",
            start_date="2023-12-29",
            end_date="2024-01-03",
            parallel=2,
        )

        # Assert - 验证正确处理
        assert result.total_dates > 0
        assert result.success_count == 4
        assert mock_coordinator.ingest_date.call_count == 4

    def test_backfill_missing_parallel_execution(
        self,
        backfill_manager,
        mock_coordinator,
        mock_metadata_service,
        mock_ingestion_log_store,
    ) -> None:
        """测试 backfill_missing 并行执行。"""
        # Arrange
        mock_metadata_service.list_trading_days.return_value = [
            "2024-12-23",
            "2024-12-24",
            "2024-12-25",
            "2024-12-26",
            "2024-12-27",
        ]

        # 已摄取2个日期，缺失3个
        mock_ingestion_log_store.list_ingested_dates.return_value = [
            "2024-12-23",
            "2024-12-27",
        ]

        mock_coordinator.ingest_date.side_effect = [
            IngestionResult(
                dataset="stock_daily",
                trade_date=date,
                status="success",
                row_count=1000,
            )
            for date in ["2024-12-24", "2024-12-25", "2024-12-26"]
        ]

        # Act
        result = backfill_manager.backfill_missing(
            dataset="stock_daily",
            parallel=2,
        )

        # Assert
        assert result.total_dates == 3
        assert result.success_count == 3
        assert mock_coordinator.ingest_date.call_count == 3

    def test_backfill_missing_empty_calendar(
        self,
        backfill_manager,
        mock_metadata_service,
    ) -> None:
        """测试当日历没有数据时的处理。"""
        # Arrange - 日历为空
        mock_metadata_service.calendar.get_first_trading_day.return_value = None
        mock_metadata_service.get_last_trading_day.return_value = None

        # Act
        result = backfill_manager.backfill_missing(dataset="stock_daily")

        # Assert
        assert result.total_dates == 0
        assert result.success_count == 0
        assert result.skipped_count == 0
        assert result.failed_count == 0

    def test_backfill_missing_calendar_has_no_trading_days(
        self,
        backfill_manager,
        mock_metadata_service,
    ) -> None:
        """测试当日历有首尾日期但没有交易日时的处理。"""
        # Arrange - 有首尾日期，但没有交易日
        mock_metadata_service.calendar.get_first_trading_day.return_value = "2024-12-01"
        mock_metadata_service.get_last_trading_day.return_value = "2024-12-31"
        mock_metadata_service.list_trading_days.return_value = []

        # Act
        result = backfill_manager.backfill_missing(dataset="stock_daily")

        # Assert
        assert result.total_dates == 0
        assert result.success_count == 0
        assert result.skipped_count == 0
        assert result.failed_count == 0

    def test_backfill_range_propagates_coordinator_error(
        self,
        backfill_manager,
        mock_coordinator,
        mock_metadata_service,
    ) -> None:
        """测试 coordinator 错误传播。"""
        # Arrange
        mock_metadata_service.list_trading_days.return_value = [
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
            Exception("Network error"),
        ]

        # Act & Assert
        with pytest.raises(Exception, match="Network error"):
            backfill_manager.backfill_range(
                dataset="stock_daily",
                start_date="2024-12-25",
                end_date="2024-12-26",
            )
