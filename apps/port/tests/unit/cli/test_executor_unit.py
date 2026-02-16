"""CLIExecutor 单元测试."""

from unittest.mock import MagicMock

import pytest
from ditto_port.cli.executor import CLIExecutor


@pytest.fixture
def mock_coordinator() -> MagicMock:
    """Mock IngestionCoordinator."""
    return MagicMock()


@pytest.fixture
def mock_backfill_manager() -> MagicMock:
    """Mock BackfillManager."""
    return MagicMock()


@pytest.mark.unit
def test_executor_init(
    mock_coordinator: MagicMock,
    mock_backfill_manager: MagicMock,
) -> None:
    """测试 CLIExecutor 初始化."""
    executor = CLIExecutor(
        coordinator=mock_coordinator,
        backfill_manager=mock_backfill_manager,
    )
    assert executor is not None
    assert executor.coordinator is mock_coordinator
    assert executor.backfill_manager is mock_backfill_manager


@pytest.mark.unit
def test_ingest_daily_success(
    mock_coordinator: MagicMock,
    mock_backfill_manager: MagicMock,
) -> None:
    """测试 ingest_daily 成功场景."""
    # Mock IngestionCoordinator.ingest_date 返回成功结果
    mock_result = MagicMock()
    mock_result.status = "success"
    mock_result.trade_date = "2024-01-02"
    mock_result.dataset = "stock_daily"
    mock_result.row_count = 5000
    mock_result.message = "数据摄取成功"
    mock_result.error = None
    mock_result.checksum = "abc123"
    mock_coordinator.ingest_date.return_value = mock_result

    executor = CLIExecutor(
        coordinator=mock_coordinator,
        backfill_manager=mock_backfill_manager,
    )
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
def test_ingest_daily_skipped(
    mock_coordinator: MagicMock,
    mock_backfill_manager: MagicMock,
) -> None:
    """测试 ingest_daily 跳过场景."""
    mock_result = MagicMock()
    mock_result.status = "skipped"
    mock_result.trade_date = "2024-01-02"
    mock_result.dataset = "stock_daily"
    mock_result.row_count = None
    mock_result.message = "数据已存在且摄取成功"
    mock_result.error = None
    mock_coordinator.ingest_date.return_value = mock_result

    executor = CLIExecutor(
        coordinator=mock_coordinator,
        backfill_manager=mock_backfill_manager,
    )
    result = executor.ingest_daily("stock_daily", "2024-01-02", force=False)

    assert result["status"] == "skipped"
    assert result["message"] == "数据已存在且摄取成功"
    assert result["row_count"] is None


@pytest.mark.unit
def test_ingest_daily_failed(
    mock_coordinator: MagicMock,
    mock_backfill_manager: MagicMock,
) -> None:
    """测试 ingest_daily 失败场景."""
    mock_result = MagicMock()
    mock_result.status = "failed"
    mock_result.trade_date = "2024-01-02"
    mock_result.dataset = "stock_daily"
    mock_result.row_count = None
    mock_result.message = "获取数据失败: 网络错误"
    mock_result.error = "FETCH_ERROR"
    mock_coordinator.ingest_date.return_value = mock_result

    executor = CLIExecutor(
        coordinator=mock_coordinator,
        backfill_manager=mock_backfill_manager,
    )
    result = executor.ingest_daily("stock_daily", "2024-01-02", force=False)

    assert result["status"] == "failed"
    assert result["error"] == "FETCH_ERROR"
    assert "网络错误" in result["message"]


@pytest.mark.unit
def test_backfill_range_success(
    mock_coordinator: MagicMock,
    mock_backfill_manager: MagicMock,
) -> None:
    """测试 backfill_range 成功场景."""
    # Mock backfill manager
    mock_backfill_result = MagicMock()
    mock_backfill_result.dataset = "stock_daily"
    mock_backfill_result.total_dates = 5
    mock_backfill_result.success_count = 4
    mock_backfill_result.skipped_count = 1
    mock_backfill_result.failed_count = 0
    mock_backfill_manager.backfill_range.return_value = mock_backfill_result

    executor = CLIExecutor(
        coordinator=mock_coordinator,
        backfill_manager=mock_backfill_manager,
    )
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
def test_backfill_range_with_failures(
    mock_coordinator: MagicMock,
    mock_backfill_manager: MagicMock,
) -> None:
    """测试 backfill_range 带失败的场景."""
    mock_backfill_result = MagicMock()
    mock_backfill_result.dataset = "stock_daily"
    mock_backfill_result.total_dates = 5
    mock_backfill_result.success_count = 3
    mock_backfill_result.skipped_count = 0
    mock_backfill_result.failed_count = 2
    mock_backfill_result.results = []
    mock_backfill_manager.backfill_range.return_value = mock_backfill_result

    executor = CLIExecutor(
        coordinator=mock_coordinator,
        backfill_manager=mock_backfill_manager,
    )
    result = executor.backfill_range(
        "stock_daily", "2024-01-01", "2024-01-05", parallel=1
    )

    assert result["failed_count"] == 2
    assert result["success_count"] == 3


@pytest.mark.unit
def test_ingest_daily_with_force(
    mock_coordinator: MagicMock,
    mock_backfill_manager: MagicMock,
) -> None:
    """测试 ingest_daily 强制摄取场景."""
    mock_result = MagicMock()
    mock_result.status = "success"
    mock_result.trade_date = "2024-01-02"
    mock_result.dataset = "stock_daily"
    mock_result.row_count = 5000
    mock_result.message = "强制摄取成功"
    mock_result.error = None
    mock_coordinator.ingest_date.return_value = mock_result

    executor = CLIExecutor(
        coordinator=mock_coordinator,
        backfill_manager=mock_backfill_manager,
    )
    result = executor.ingest_daily("stock_daily", "2024-01-02", force=True)

    assert result["status"] == "success"
    mock_coordinator.ingest_date.assert_called_once_with(
        "stock_daily", "2024-01-02", True
    )
