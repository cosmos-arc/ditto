"""Pytest configuration for unit tests.

这个文件为单元测试禁用 Prefect API 服务器，提高测试性能。

这个文件为 tests/unit/ 目录下的所有测试自动添加 @pytest.mark.unit marker。
"""

from collections.abc import Generator
from unittest.mock import MagicMock

import prefect
import prefect.flows
import pytest


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """为 unit 目录下的所有测试自动添加 unit marker.

    Args:
        items: pytest 收集到的所有测试项
    """
    for item in items:
        # 检查测试文件是否在 unit 目录下且没有 unit marker
        is_unit_path = "/tests/unit/" in str(item.fspath) or "\\tests\\unit\\" in str(
            item.fspath
        )
        has_unit_marker = "unit" in [mark.name for mark in item.iter_markers()]

        if is_unit_path and not has_unit_marker:
            item.add_marker(pytest.mark.unit)


# ===================================================================
# Mock Prefect 装饰器（仅在单元测试中）
# ===================================================================
# 原始装饰器保存（用于恢复）
_original_flow_decorator = prefect.flows.flow
_original_task_decorator = prefect.tasks.task


def _mock_flow_decorator(*args, **kwargs):
    """Mock @flow decorator that returns the function unchanged."""

    def decorator(func):
        return func

    # Support @flow() and @flow syntax
    if args and callable(args[0]):
        return args[0]  # Direct @flow without parentheses
    return decorator


def _mock_task_decorator(*args, **kwargs):
    """Mock @task decorator that returns the function unchanged."""

    def decorator(func):
        return func

    # Support @task() and @task syntax
    if args and callable(args[0]):
        return args[0]  # Direct @task without parentheses
    return decorator


@pytest.fixture(autouse=True)
def apply_prefect_mocks_and_disable_api_server() -> Generator[None, None, None]:
    """应用 Prefect mock 并禁用 API 服务器（仅限单元测试）.

    通过 autouse fixture 确保只有单元测试使用 mock，
    避免影响集成测试。
    """
    # 应用 mock
    import prefect

    prefect.flows.flow = _mock_flow_decorator
    prefect.tasks.task = _mock_task_decorator

    # 禁用 API 服务器
    import prefect.settings

    with prefect.settings.temporary_settings(
        updates={prefect.settings.PREFECT_API_URL: None}
    ):
        yield

    # 恢复原始装饰器
    prefect.flows.flow = _original_flow_decorator
    prefect.tasks.task = _original_task_decorator


# 移除原来的全局 mock 应用，改为通过 fixture 应用
# prefect.flows.flow = _mock_flow_decorator
# prefect.tasks.task = _mock_task_decorator


@pytest.fixture
def app_ctx() -> MagicMock:
    """CLI 测试用的 AppContext mock (兼容旧测试)."""
    from unittest.mock import MagicMock

    mock = MagicMock()

    # DataHub mock
    mock.hub.calendar_store.is_trading_day.return_value = True
    mock.hub.calendar_store.get_range.return_value = ["2024-01-02", "2024-01-03"]
    mock.hub.ingestion_log_store.get_ingested_dates.return_value = []
    mock.hub.ingestion_log_store.save_log.return_value = None

    # DataSource mock (已废弃 - 仅用于向后兼容)
    mock.source.fetch_stock_daily.return_value = None
    mock.source.fetch_etf_daily.return_value = None
    mock.source.fetch_calendar.return_value = None
    mock.source.fetch_stock_basic.return_value = None
    mock.source.fetch_etf_basic.return_value = None
    mock.source.fetch_adj_factor.return_value = None
    mock.source.fetch_fund_adj.return_value = None

    return mock


@pytest.fixture
def mock_hub() -> MagicMock:
    """DataHub mock 用于 CLIExecutor 测试."""
    from unittest.mock import MagicMock

    mock = MagicMock()
    mock.calendar_store.is_trading_day.return_value = True
    mock.calendar_store.get_range.return_value = ["2024-01-02", "2024-01-03"]
    mock.ingestion_log_store.get_ingested_dates.return_value = []
    mock.ingestion_log_store.save_log.return_value = None

    return mock
