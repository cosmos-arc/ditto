"""CLIExecutor 单元测试."""

import pytest
from ditto_datahub.models import Source
from ditto_port.cli.executor import CLIExecutor
from pytest_mock import MockerFixture


@pytest.mark.unit
def test_executor_init_with_services(
    mock_metadata_service,
    mock_market_service,
    mock_fundamental_service,
    mock_capital_service,
    mock_macro_service,
    mock_source_service,
    mock_ingestion_log_service,
):
    """测试 CLIExecutor 初始化"""
    # 测试初始化不抛出异常
    with CLIExecutor.create(
        metadata_service=mock_metadata_service,
        market_service=mock_market_service,
        fundamental_service=mock_fundamental_service,
        capital_service=mock_capital_service,
        macro_service=mock_macro_service,
        source_service=mock_source_service,
        ingestion_log_service=mock_ingestion_log_service,
        source_name=Source.TUSHARE,
    ) as executor:
        assert executor is not None
        assert executor._source_name == Source.TUSHARE


@pytest.mark.unit
def test_ingest_daily_success(
    mock_metadata_service,
    mock_market_service,
    mock_fundamental_service,
    mock_capital_service,
    mock_macro_service,
    mock_source_service,
    mock_ingestion_log_service,
    mocker: MockerFixture,
):
    """测试 ingest_daily 成功场景"""
    # Mock IngestionCoordinator.ingest_date 返回成功结果
    mock_result = mocker.Mock()
    mock_result.status = "success"
    mock_result.trade_date = "2024-01-02"
    mock_result.dataset = "stock_daily"
    mock_result.row_count = 5000
    mock_result.message = "数据摄取成功"
    mock_result.error = None
    mock_result.checksum = "abc123"

    # Mock IngestionCoordinator.ingest_date 方法
    mocker.patch(
        "ditto_port.services.ingestion.coordinator.IngestionCoordinator.ingest_date",
        return_value=mock_result,
    )

    # Mock BackfillManager
    mock_backfill_mgr = mocker.Mock()
    mocker.patch(
        "ditto_port.cli.executor.BackfillManager", return_value=mock_backfill_mgr
    )

    with CLIExecutor.create(
        metadata_service=mock_metadata_service,
        market_service=mock_market_service,
        fundamental_service=mock_fundamental_service,
        capital_service=mock_capital_service,
        macro_service=mock_macro_service,
        source_service=mock_source_service,
        ingestion_log_service=mock_ingestion_log_service,
        source_name=Source.TUSHARE,
    ) as executor:
        result = executor.ingest_daily("stock_daily", "2024-01-02", force=False)

        assert result["dataset"] == "stock_daily"
        assert result["trade_date"] == "2024-01-02"
        assert result["status"] == "success"
        assert result["row_count"] == 5000
        assert result["message"] == "数据摄取成功"
        assert result["error"] is None


@pytest.mark.unit
def test_ingest_daily_skipped(
    mock_metadata_service,
    mock_market_service,
    mock_fundamental_service,
    mock_capital_service,
    mock_macro_service,
    mock_source_service,
    mock_ingestion_log_service,
    mocker: MockerFixture,
):
    """测试 ingest_daily 跳过场景"""
    mock_result = mocker.Mock()
    mock_result.status = "skipped"
    mock_result.trade_date = "2024-01-02"
    mock_result.dataset = "stock_daily"
    mock_result.row_count = None
    mock_result.message = "数据已存在且摄取成功"
    mock_result.error = None

    mocker.patch(
        "ditto_port.services.ingestion.coordinator.IngestionCoordinator.ingest_date",
        return_value=mock_result,
    )

    mock_backfill_mgr = mocker.Mock()
    mocker.patch(
        "ditto_port.cli.executor.BackfillManager", return_value=mock_backfill_mgr
    )

    with CLIExecutor.create(
        metadata_service=mock_metadata_service,
        market_service=mock_market_service,
        fundamental_service=mock_fundamental_service,
        capital_service=mock_capital_service,
        macro_service=mock_macro_service,
        source_service=mock_source_service,
        ingestion_log_service=mock_ingestion_log_service,
        source_name=Source.TUSHARE,
    ) as executor:
        result = executor.ingest_daily("stock_daily", "2024-01-02", force=False)

        assert result["status"] == "skipped"
        assert result["message"] == "数据已存在且摄取成功"
        assert result["row_count"] is None


@pytest.mark.unit
def test_ingest_daily_failed(
    mock_metadata_service,
    mock_market_service,
    mock_fundamental_service,
    mock_capital_service,
    mock_macro_service,
    mock_source_service,
    mock_ingestion_log_service,
    mocker: MockerFixture,
):
    """测试 ingest_daily 失败场景"""
    mock_result = mocker.Mock()
    mock_result.status = "failed"
    mock_result.trade_date = "2024-01-02"
    mock_result.dataset = "stock_daily"
    mock_result.row_count = None
    mock_result.message = "获取数据失败: 网络错误"
    mock_result.error = "FETCH_ERROR"

    mocker.patch(
        "ditto_port.services.ingestion.coordinator.IngestionCoordinator.ingest_date",
        return_value=mock_result,
    )

    mock_backfill_mgr = mocker.Mock()
    mocker.patch(
        "ditto_port.cli.executor.BackfillManager", return_value=mock_backfill_mgr
    )

    with CLIExecutor.create(
        metadata_service=mock_metadata_service,
        market_service=mock_market_service,
        fundamental_service=mock_fundamental_service,
        capital_service=mock_capital_service,
        macro_service=mock_macro_service,
        source_service=mock_source_service,
        ingestion_log_service=mock_ingestion_log_service,
        source_name=Source.TUSHARE,
    ) as executor:
        result = executor.ingest_daily("stock_daily", "2024-01-02", force=False)

        assert result["status"] == "failed"
        assert result["error"] == "FETCH_ERROR"
        assert "网络错误" in result["message"]


@pytest.mark.unit
def test_backfill_range_success(
    mock_metadata_service,
    mock_market_service,
    mock_fundamental_service,
    mock_capital_service,
    mock_macro_service,
    mock_source_service,
    mock_ingestion_log_service,
    mocker: MockerFixture,
):
    """测试 backfill_range 成功场景"""
    # Mock backfill manager
    mock_backfill_mgr = mocker.Mock()
    mock_backfill_result = mocker.Mock()
    mock_backfill_result.dataset = "stock_daily"
    mock_backfill_result.total_dates = 5
    mock_backfill_result.success_count = 4
    mock_backfill_result.skipped_count = 1
    mock_backfill_result.failed_count = 0
    mock_backfill_mgr.backfill_range.return_value = mock_backfill_result
    mocker.patch(
        "ditto_port.cli.executor.BackfillManager", return_value=mock_backfill_mgr
    )

    with CLIExecutor.create(
        metadata_service=mock_metadata_service,
        market_service=mock_market_service,
        fundamental_service=mock_fundamental_service,
        capital_service=mock_capital_service,
        macro_service=mock_macro_service,
        source_service=mock_source_service,
        ingestion_log_service=mock_ingestion_log_service,
        source_name=Source.TUSHARE,
    ) as executor:
        result = executor.backfill_range(
            "stock_daily", "2024-01-01", "2024-01-05", parallel=2
        )

        assert result["dataset"] == "stock_daily"
        assert result["total_dates"] == 5
        assert result["success_count"] == 4
        assert result["skipped_count"] == 1
        assert result["failed_count"] == 0

        mock_backfill_mgr.backfill_range.assert_called_once_with(
            dataset="stock_daily",
            start_date="2024-01-01",
            end_date="2024-01-05",
            parallel=2,
        )


@pytest.mark.unit
def test_backfill_range_with_failures(
    mock_metadata_service,
    mock_market_service,
    mock_fundamental_service,
    mock_capital_service,
    mock_macro_service,
    mock_source_service,
    mock_ingestion_log_service,
    mocker: MockerFixture,
):
    """测试 backfill_range 带失败的场景"""
    mock_backfill_mgr = mocker.Mock()
    mock_backfill_result = mocker.Mock()
    mock_backfill_result.dataset = "stock_daily"
    mock_backfill_result.total_dates = 5
    mock_backfill_result.success_count = 3
    mock_backfill_result.skipped_count = 0
    mock_backfill_result.failed_count = 2
    mock_backfill_result.results = []
    mock_backfill_mgr.backfill_range.return_value = mock_backfill_result
    mocker.patch(
        "ditto_port.cli.executor.BackfillManager", return_value=mock_backfill_mgr
    )

    with CLIExecutor.create(
        metadata_service=mock_metadata_service,
        market_service=mock_market_service,
        fundamental_service=mock_fundamental_service,
        capital_service=mock_capital_service,
        macro_service=mock_macro_service,
        source_service=mock_source_service,
        ingestion_log_service=mock_ingestion_log_service,
        source_name=Source.TUSHARE,
    ) as executor:
        result = executor.backfill_range(
            "stock_daily", "2024-01-01", "2024-01-05", parallel=1
        )

        assert result["failed_count"] == 2
        assert result["success_count"] == 3
