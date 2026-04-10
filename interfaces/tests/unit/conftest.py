"""Pytest configuration for unit tests.

这个文件为单元测试禁用 Prefect API 服务器，提高测试性能。

这个文件为 tests/unit/ 目录下的所有测试自动添加 @pytest.mark.unit marker。
"""

from collections.abc import Generator
from unittest.mock import MagicMock, Mock

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
# Mock Prefect 装饰器（必须在模块导入前应用）
# ===================================================================
# 保存原始装饰器
_original_flow_decorator = prefect.flows.flow
_original_task_decorator = prefect.tasks.task


class MockTask:
    """Mock task that mimics Prefect Task interface."""

    def __init__(self, func):
        self.func = func
        # 复制函数的关键属性
        self.__name__ = getattr(func, "__name__", "mock_task")
        self.__doc__ = getattr(func, "__doc__", None)
        self.name = self.__name__
        self._is_prefect_task = True

    def __call__(self, *args, **kwargs):
        # 过滤掉 Prefect 特有的参数
        filtered_kwargs = {
            k: v
            for k, v in kwargs.items()
            if k not in ("wait_for", "return_state", "refresh_cache")
        }
        return self.func(*args, **filtered_kwargs)

    def submit(self, *args, **kwargs):
        """Mock submit that returns a future-like object."""
        # 过滤掉 Prefect 特有的参数
        filtered_kwargs = {
            k: v
            for k, v in kwargs.items()
            if k not in ("wait_for", "return_state", "refresh_cache")
        }
        result = self.func(*args, **filtered_kwargs)
        future = Mock()
        future.result = Mock(return_value=result)
        return future

    def fn(self):
        """Return the underlying function."""
        return self.func


def _mock_flow_decorator(*args, **kwargs):
    """Mock @flow decorator that returns the function unchanged."""

    def decorator(func):
        # 添加 flow 的常用属性
        func.is_flow = True
        func.name = getattr(func, "__name__", "mock_flow")
        return func

    # Support @flow() and @flow syntax
    if args and callable(args[0]):
        return args[0]  # Direct @flow without parentheses
    return decorator


def _mock_task_decorator(*args, **kwargs):
    """Mock @task decorator that returns a MockTask."""

    def decorator(func):
        return MockTask(func)

    # Support @task() and @task syntax
    if args and callable(args[0]):
        return MockTask(args[0])  # Direct @task without parentheses
    return decorator


# 在模块级别立即应用 mock（在任何测试模块导入之前）
prefect.flows.flow = _mock_flow_decorator
prefect.tasks.task = _mock_task_decorator


@pytest.fixture(autouse=True)
def disable_prefect_api_server() -> Generator[None, None, None]:
    """禁用 Prefect API 服务器（单元测试不需要）."""
    import prefect.settings

    with prefect.settings.temporary_settings(
        updates={prefect.settings.PREFECT_API_URL: None}
    ):
        yield


@pytest.fixture
def app_ctx() -> MagicMock:
    """CLI 测试用的 AppContext mock (兼容旧测试)."""
    from unittest.mock import MagicMock

    mock = MagicMock()

    # Data mock
    mock.hub.calendar_store.is_trading_day.return_value = True
    mock.hub.calendar_store.get_range.return_value = ["2024-01-02", "2024-01-03"]
    mock.hub.ingestion_log_store.list_ingested_dates.return_value = []
    mock.hub.ingestion_log_store.save_log.return_value = None

    return mock


@pytest.fixture
def mock_services() -> dict[str, MagicMock]:
    """Service mocks 用于 CLIExecutor 测试."""
    from unittest.mock import MagicMock

    return {
        "metadata_service": MagicMock(),
        "market_service": MagicMock(),
        "fundamental_service": MagicMock(),
        "capital_service": MagicMock(),
        "macro_service": MagicMock(),
        "source_service": MagicMock(),
        "ingestion_log_service": MagicMock(),
    }


@pytest.fixture
def mock_metadata_service(mock_services: dict[str, MagicMock]) -> MagicMock:
    """MetadataService mock."""
    return mock_services["metadata_service"]


@pytest.fixture
def mock_market_service(mock_services: dict[str, MagicMock]) -> MagicMock:
    """MarketService mock."""
    return mock_services["market_service"]


@pytest.fixture
def mock_fundamental_service(mock_services: dict[str, MagicMock]) -> MagicMock:
    """FundamentalService mock."""
    return mock_services["fundamental_service"]


@pytest.fixture
def mock_capital_service(mock_services: dict[str, MagicMock]) -> MagicMock:
    """CapitalService mock."""
    return mock_services["capital_service"]


@pytest.fixture
def mock_macro_service(mock_services: dict[str, MagicMock]) -> MagicMock:
    """MacroService mock."""
    return mock_services["macro_service"]


@pytest.fixture
def mock_source_service(mock_services: dict[str, MagicMock]) -> MagicMock:
    """SourceService mock."""
    return mock_services["source_service"]


@pytest.fixture
def mock_ingestion_log_service(mock_services: dict[str, MagicMock]) -> MagicMock:
    """IngestionLogService mock."""
    return mock_services["ingestion_log_service"]
