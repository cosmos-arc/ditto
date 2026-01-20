"""CLIExecutor 单元测试."""

from unittest.mock import Mock, patch

import pytest
from ditto_datahub.models import Source
from ditto_port.cli.executor import CLIExecutor


@pytest.mark.unit
def test_executor_init_with_hub(mock_hub):
    """测试 CLIExecutor 初始化"""
    # 测试初始化不抛出异常
    executor = CLIExecutor(hub=mock_hub, source_name=Source.TUSHARE)
    assert executor is not None
    assert executor._hub is mock_hub
    assert executor._source_name == Source.TUSHARE


@pytest.mark.unit
@patch("ditto_port.cli.executor.create_coordinator")
@patch("ditto_port.cli.executor.BackfillManager")
def test_ingest_daily_success(mock_backfill_mgr_cls, mock_create_coord, mock_hub):
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

    # 设置 create_coordinator mock 上下文管理器
    mock_context = Mock()
    mock_context.__enter__ = Mock(return_value=mock_coordinator)
    mock_context.__exit__ = Mock(return_value=None)
    mock_create_coord.return_value = mock_context

    # Mock BackfillManager
    mock_backfill_mgr = Mock()
    mock_backfill_mgr_cls.return_value = mock_backfill_mgr

    with CLIExecutor.create(hub=mock_hub, source_name=Source.TUSHARE) as executor:
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
@patch("ditto_port.cli.executor.create_coordinator")
@patch("ditto_port.cli.executor.BackfillManager")
def test_ingest_daily_skipped(mock_backfill_mgr_cls, mock_create_coord, mock_hub):
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

    mock_context = Mock()
    mock_context.__enter__ = Mock(return_value=mock_coordinator)
    mock_context.__exit__ = Mock(return_value=None)
    mock_create_coord.return_value = mock_context

    mock_backfill_mgr = Mock()
    mock_backfill_mgr_cls.return_value = mock_backfill_mgr

    with CLIExecutor.create(hub=mock_hub, source_name=Source.TUSHARE) as executor:
        result = executor.ingest_daily("stock_daily", "2024-01-02", force=False)

        assert result["status"] == "skipped"
        assert result["message"] == "数据已存在且摄取成功"
        assert result["row_count"] is None


@pytest.mark.unit
@patch("ditto_port.cli.executor.create_coordinator")
@patch("ditto_port.cli.executor.BackfillManager")
def test_ingest_daily_failed(mock_backfill_mgr_cls, mock_create_coord, mock_hub):
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

    mock_context = Mock()
    mock_context.__enter__ = Mock(return_value=mock_coordinator)
    mock_context.__exit__ = Mock(return_value=None)
    mock_create_coord.return_value = mock_context

    mock_backfill_mgr = Mock()
    mock_backfill_mgr_cls.return_value = mock_backfill_mgr

    with CLIExecutor.create(hub=mock_hub, source_name=Source.TUSHARE) as executor:
        result = executor.ingest_daily("stock_daily", "2024-01-02", force=False)

        assert result["status"] == "failed"
        assert result["error"] == "FETCH_ERROR"
        assert "网络错误" in result["message"]


@pytest.mark.unit
@patch("ditto_port.cli.executor.create_coordinator")
@patch("ditto_port.cli.executor.BackfillManager")
def test_backfill_range_success(mock_backfill_mgr_cls, mock_create_coord, mock_hub):
    """测试 backfill_range 成功场景"""
    # Mock coordinator
    mock_coordinator = Mock()

    mock_context = Mock()
    mock_context.__enter__ = Mock(return_value=mock_coordinator)
    mock_context.__exit__ = Mock(return_value=None)
    mock_create_coord.return_value = mock_context

    # Mock backfill manager
    mock_backfill_mgr = Mock()
    mock_backfill_result = Mock()
    mock_backfill_result.dataset = "stock_daily"
    mock_backfill_result.total_dates = 5
    mock_backfill_result.success_count = 4
    mock_backfill_result.skipped_count = 1
    mock_backfill_result.failed_count = 0
    mock_backfill_mgr.backfill_range.return_value = mock_backfill_result
    mock_backfill_mgr_cls.return_value = mock_backfill_mgr

    with CLIExecutor.create(hub=mock_hub, source_name=Source.TUSHARE) as executor:
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
@patch("ditto_port.cli.executor.create_coordinator")
@patch("ditto_port.cli.executor.BackfillManager")
def test_backfill_range_with_failures(
    mock_backfill_mgr_cls, mock_create_coord, mock_hub
):
    """测试 backfill_range 带失败的场景"""
    mock_coordinator = Mock()

    mock_context = Mock()
    mock_context.__enter__ = Mock(return_value=mock_coordinator)
    mock_context.__exit__ = Mock(return_value=None)
    mock_create_coord.return_value = mock_context

    mock_backfill_mgr = Mock()
    mock_backfill_result = Mock()
    mock_backfill_result.dataset = "stock_daily"
    mock_backfill_result.total_dates = 5
    mock_backfill_result.success_count = 3
    mock_backfill_result.skipped_count = 0
    mock_backfill_result.failed_count = 2
    mock_backfill_result.results = []
    mock_backfill_mgr.backfill_range.return_value = mock_backfill_result
    mock_backfill_mgr_cls.return_value = mock_backfill_mgr

    with CLIExecutor.create(hub=mock_hub, source_name=Source.TUSHARE) as executor:
        result = executor.backfill_range(
            "stock_daily", "2024-01-01", "2024-01-05", parallel=1
        )

        assert result["failed_count"] == 2
        assert result["success_count"] == 3
