"""Pytest configuration for unit tests.

这个文件为单元测试禁用 Prefect API 服务器，提高测试性能。
"""

from collections.abc import Generator
from unittest.mock import MagicMock

import pytest


@pytest.fixture(autouse=True)
def no_api_server() -> Generator[None, None, None]:
    """禁用 API 服务器，加速单元测试.

    通过设置 PREFECT_API_URL=None，避免每个测试都启动独立的 API 服务器。
    这是 Prefect 官方推荐的单元测试优化方式。
    """
    import prefect.settings

    with prefect.settings.temporary_settings(
        updates={prefect.settings.PREFECT_API_URL: None}
    ):
        yield


@pytest.fixture
def app_ctx() -> MagicMock:
    """CLI 测试用的 AppContext mock.

    提供模拟的 DataHub 和 DataSource，用于 CLIExecutor 测试。
    """
    from unittest.mock import MagicMock

    mock = MagicMock()

    # DataHub mock
    mock.hub.calendar_store.is_trading_day.return_value = True
    mock.hub.calendar_store.get_range.return_value = ["2024-01-02", "2024-01-03"]
    mock.hub.ingestion_log.get_ingested_dates.return_value = []
    mock.hub.ingestion_log.save_log.return_value = None

    # DataSource mock
    mock.source.fetch_stock_daily.return_value = None
    mock.source.fetch_etf_daily.return_value = None
    mock.source.fetch_calendar.return_value = None
    mock.source.fetch_stock_basic.return_value = None
    mock.source.fetch_etf_basic.return_value = None
    mock.source.fetch_adj_factor.return_value = None
    mock.source.fetch_fund_adj.return_value = None

    return mock
