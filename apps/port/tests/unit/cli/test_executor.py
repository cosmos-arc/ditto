"""CLIExecutor 单元测试."""

from unittest.mock import Mock

import pytest
from ditto_port.cli.executor import CLIExecutor


@pytest.mark.unit
def test_executor_init(app_ctx):
    """测试 CLIExecutor 初始化"""
    # 测试初始化不抛出异常
    executor = CLIExecutor(app_ctx)
    assert executor is not None
    assert executor._app_ctx is app_ctx
    assert executor._hub is app_ctx.hub
    assert executor._source is app_ctx.source


@pytest.mark.unit
def test_ingest_daily_success(app_ctx):
    """测试 ingest_daily 成功场景"""
    # Mock coordinator 返回成功结果
    mock_coordinator = Mock()
    mock_result = Mock()
    mock_result.status = "success"
    mock_result.trade_date = "2024-01-02"
    mock_result.dataset = "stock_daily"
    mock_result.row_count = 5000
    mock_result.message = "数据摄取成功"
    mock_result.error = None
    mock_result.checksum = "abc123"
    mock_coordinator.ingest_date.return_value = mock_result

    executor = CLIExecutor(app_ctx)
    executor._coordinator = mock_coordinator

    result = executor.ingest_daily("stock_daily", "2024-01-02", force=False)

    assert result["dataset"] == "stock_daily"
    assert result["trade_date"] == "2024-01-02"
    assert result["status"] == "success"
    assert result["row_count"] == 5000
    assert result["message"] == "数据摄取成功"
    assert result["error"] is None

    mock_coordinator.ingest_date.assert_called_once_with(
        "stock_daily", "2024-01-02", False
    )


@pytest.mark.unit
def test_ingest_daily_skipped(app_ctx):
    """测试 ingest_daily 跳过场景"""
    mock_coordinator = Mock()
    mock_result = Mock()
    mock_result.status = "skipped"
    mock_result.trade_date = "2024-01-02"
    mock_result.dataset = "stock_daily"
    mock_result.row_count = None
    mock_result.message = "数据已存在且摄取成功"
    mock_result.error = None
    mock_coordinator.ingest_date.return_value = mock_result

    executor = CLIExecutor(app_ctx)
    executor._coordinator = mock_coordinator

    result = executor.ingest_daily("stock_daily", "2024-01-02", force=False)

    assert result["status"] == "skipped"
    assert result["message"] == "数据已存在且摄取成功"
    assert result["row_count"] is None


@pytest.mark.unit
def test_ingest_daily_failed(app_ctx):
    """测试 ingest_daily 失败场景"""
    mock_coordinator = Mock()
    mock_result = Mock()
    mock_result.status = "failed"
    mock_result.trade_date = "2024-01-02"
    mock_result.dataset = "stock_daily"
    mock_result.row_count = None
    mock_result.message = "获取数据失败: 网络错误"
    mock_result.error = "FETCH_ERROR"
    mock_coordinator.ingest_date.return_value = mock_result

    executor = CLIExecutor(app_ctx)
    executor._coordinator = mock_coordinator

    result = executor.ingest_daily("stock_daily", "2024-01-02", force=False)

    assert result["status"] == "failed"
    assert result["error"] == "FETCH_ERROR"
    assert "网络错误" in result["message"]


@pytest.mark.unit
def test_backfill_range_success(app_ctx):
    """测试 backfill_range 成功场景"""
    mock_backfill_manager = Mock()

    # 创建多个 mock 结果
    mock_results = []
    for i in range(5):
        mock_result = Mock()
        mock_result.status = "success" if i < 4 else "skipped"
        mock_results.append(mock_result)

    mock_backfill_result = Mock()
    mock_backfill_result.dataset = "stock_daily"
    mock_backfill_result.total_dates = 5
    mock_backfill_result.success_count = 4
    mock_backfill_result.skipped_count = 1
    mock_backfill_result.failed_count = 0
    mock_backfill_result.results = mock_results
    mock_backfill_manager.backfill_range.return_value = mock_backfill_result

    executor = CLIExecutor(app_ctx)
    executor._backfill_manager = mock_backfill_manager

    result = executor.backfill_range(
        "stock_daily", "2024-01-01", "2024-01-05", parallel=2
    )

    assert result["dataset"] == "stock_daily"
    assert result["total_dates"] == 5
    assert result["success_count"] == 4
    assert result["skipped_count"] == 1
    assert result["failed_count"] == 0

    mock_backfill_manager.backfill_range.assert_called_once_with(
        dataset="stock_daily",
        start_date="2024-01-01",
        end_date="2024-01-05",
        parallel=2,
    )


@pytest.mark.unit
def test_backfill_range_with_failures(app_ctx):
    """测试 backfill_range 带失败的场景"""
    mock_backfill_manager = Mock()

    mock_backfill_result = Mock()
    mock_backfill_result.dataset = "stock_daily"
    mock_backfill_result.total_dates = 5
    mock_backfill_result.success_count = 3
    mock_backfill_result.skipped_count = 0
    mock_backfill_result.failed_count = 2
    mock_backfill_result.results = []
    mock_backfill_manager.backfill_range.return_value = mock_backfill_result

    executor = CLIExecutor(app_ctx)
    executor._backfill_manager = mock_backfill_manager

    result = executor.backfill_range(
        "stock_daily", "2024-01-01", "2024-01-05", parallel=1
    )

    assert result["failed_count"] == 2
    assert result["success_count"] == 3
