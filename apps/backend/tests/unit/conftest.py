"""Pytest configuration for unit tests.

这个文件为单元测试按需启用 Prefect 装饰器 mock，提高测试性能。
mock 以两种作用域生效（#330 B1）：导入期经 layering 插件的 bracket 只覆盖
本树模块导入；执行期由下面的 autouse fixture 按测试应用/恢复——运行中调用
``create_ingest_task`` 等工厂的测试同样拿到 mock，而不是真实 Prefect Task。
两种作用域都不泄漏到其他 owner。
"""

from collections.abc import Generator
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from ditto_apps import prefect_mock
from tooling.quality.pytest_layering import register_import_bracket

_UNIT_TREE = Path(__file__).resolve().parent

register_import_bracket(_UNIT_TREE, prefect_mock.apply, prefect_mock.restore)


@pytest.fixture(autouse=True)
def disable_prefect_api_server() -> Generator[None]:
    """单测期间启用 Prefect 装饰器 mock 并禁用 API 服务器，测试后恢复."""
    import prefect.settings

    prefect_mock.apply()
    try:
        with prefect.settings.temporary_settings(
            updates={prefect.settings.PREFECT_API_URL: None}
        ):
            yield
    finally:
        prefect_mock.restore()


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
        "fundamental_store": MagicMock(),
        "capital_store": MagicMock(),
        "macro_service": MagicMock(),
        "source_accessor": MagicMock(),
        "ingestion_log_store": MagicMock(),
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
def mock_fundamental_store(mock_services: dict[str, MagicMock]) -> MagicMock:
    """FundamentalStore mock."""
    return mock_services["fundamental_store"]


@pytest.fixture
def mock_capital_store(mock_services: dict[str, MagicMock]) -> MagicMock:
    """CapitalStore mock."""
    return mock_services["capital_store"]


@pytest.fixture
def mock_macro_service(mock_services: dict[str, MagicMock]) -> MagicMock:
    """MacroService mock."""
    return mock_services["macro_service"]


@pytest.fixture
def mock_source_accessor(mock_services: dict[str, MagicMock]) -> MagicMock:
    """SourceAccessor mock."""
    return mock_services["source_accessor"]


@pytest.fixture
def mock_ingestion_log_store(mock_services: dict[str, MagicMock]) -> MagicMock:
    """IngestionLogStore mock."""
    return mock_services["ingestion_log_store"]
