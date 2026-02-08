"""pytest配置文件."""

import sqlite3
from collections.abc import Generator
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import duckdb
import pytest
from ditto_foundation.config import Settings
from ditto_foundation.config.environment import Environment
from ditto_foundation.observability.config import ObservabilityConfig
from ditto_port.testing import DatabaseManager


def pytest_configure(config) -> None:
    """在测试开始前预加载模块.

    预加载 ingestion flows 模块,避免每个测试都重新导入相同模块,
    从而减少测试执行时间（目标: 减少 1-2秒/测试）.
    """
    # 预加载 flows 模块,避免每个测试都重新导入
    # fmt: off
    # fmt: on


@pytest.fixture
def fake_time(monkeypatch: pytest.MonkeyPatch) -> None:
    """可控的时间 fixture，通过 monkeypatch 替换时间函数.

    使 time.sleep 立即完成，time.time 按预期前进，提高测试速度和确定性。
    """
    current_time = [0.0]

    def fake_sleep(seconds: float) -> None:
        current_time[0] += seconds

    def fake_time_func() -> float:
        return current_time[0]

    monkeypatch.setattr("time.sleep", fake_sleep)
    monkeypatch.setattr("time.time", fake_time_func)


@pytest.fixture
def test_settings(tmp_path: Path) -> Settings:
    """测试配置fixture.

    使用 pytest 内置 tmp_path，每个测试获得独立的 Settings 实例和临时目录。
    使用依赖注入而非环境变量，支持并行测试。

    Args:
        tmp_path: pytest 内置 fixture，每个测试自动创建独立临时目录

    Returns:
        Settings: 测试配置对象
    """
    from ditto_foundation.config.settings import ObservabilitySettings, SystemSettings

    settings = Settings(
        system=SystemSettings(environment=Environment.TESTING),
        observability=ObservabilitySettings(),
    )
    return settings


@pytest.fixture
def db_manager(tmp_path: Path) -> Generator[DatabaseManager, None, None]:
    """每个测试独立的数据库管理器.

    使用 pytest 内置 tmp_path，每个测试获得独立的数据库实例。
    支持并行测试。

    Args:
        tmp_path: pytest 内置 fixture，提供独立临时目录

    Yields:
        DatabaseManager: 数据库管理器实例
    """
    manager = DatabaseManager(database_path=tmp_path / "test.duckdb")
    yield manager
    manager.close()


@pytest.fixture
def clean_duckdb(db_manager: DatabaseManager) -> duckdb.DuckDBPyConnection:
    """提供清理后的连接."""
    db_manager.clean_duckdb()
    return db_manager.get_duckdb_conn()


@pytest.fixture
def sqlite_conn(
    tmp_path: Path,
) -> Generator[sqlite3.Connection, None, None]:
    """SQLite 连接 fixture.

    使用 pytest 内置 tmp_path，每个测试获得独立的 SQLite 数据库。

    Args:
        tmp_path: pytest 内置 fixture，提供独立临时目录
    """
    sqlite_path = tmp_path / "test.sqlite"
    conn = sqlite3.connect(str(sqlite_path))

    # 初始化表结构
    conn.execute("""
        CREATE TABLE IF NOT EXISTS trading_calendar (
            date DATE PRIMARY KEY,
            is_trading_day BOOLEAN,
            knowledge_date DATE
        )
    """)

    yield conn

    conn.close()


@pytest.fixture
def sample_etf_data() -> list[dict[str, Any]]:
    """示例ETF数据."""
    return [
        {
            "symbol": "510300",
            "name": "沪深300ETF",
            "market": "上海",
            "category": "指数型",
            "establish_date": "2012-04-26",
            "fund_manager": "柳军",
            "tracking_index": "沪深300指数",
            "knowledge_date": "2024-01-01",
        },
        {
            "symbol": "159915",
            "name": "创业板ETF",
            "market": "深圳",
            "category": "指数型",
            "establish_date": "2011-09-20",
            "fund_manager": "王军",
            "tracking_index": "创业板指数",
            "knowledge_date": "2024-01-01",
        },
    ]


@pytest.fixture
def sample_daily_data() -> list[dict[str, Any]]:
    """示例日线数据."""
    data = []
    symbol = "510300"
    for i in range(10):
        date = f"2024-01-{i + 1:02d}"
        data.append(
            {
                "symbol": symbol,
                "date": date,
                "open": 3.5 + i * 0.01,
                "high": 3.6 + i * 0.01,
                "low": 3.4 + i * 0.01,
                "close": 3.55 + i * 0.01,
                "volume": 1000000 + i * 10000,
                "knowledge_date": "2024-01-01",
            }
        )
    return data


# =============================================================================
# 可观测性 Fixtures
# =============================================================================


@pytest.fixture(autouse=True)
def reset_observability() -> Generator[None, None, None]:
    """每个测试自动重置可观测性状态."""
    from ditto_foundation import reset_for_testing

    reset_for_testing()
    yield
    reset_for_testing()


@pytest.fixture
def obs_noop() -> None:
    """静默模式 - 最快, 不输出日志."""
    from ditto_foundation import init

    config = ObservabilityConfig(
        environment=Environment.TESTING,
        pytest_running=True,
        assertions_enabled=False,
        verbose_logging=False,
        tracing_enabled=False,
        metrics_enabled=False,
    )
    init(config, force=True)


@pytest.fixture
def obs_assertions() -> None:
    """断言模式 - 可验证, 内存记录."""
    from ditto_foundation import init

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


@pytest.fixture
def mock_datahub() -> MagicMock:
    """每个测试独立的 Mock DataHub.

    使用 function 作用域确保测试隔离，支持并行测试。

    Returns:
        MagicMock: Mock DataHub 对象
    """
    mock = MagicMock()

    # Calendar mock
    mock.metadata.is_trading_day.return_value = True
    mock.calendar_store.get_first_trading_day.return_value = "2024-01-02"
    mock.calendar_store.get_last_trading_day.return_value = "2024-01-31"
    mock.calendar_store.get_range.return_value = ["2024-01-02", "2024-01-03"]

    # Ingestion log mock
    mock.ingestion_log_store.get_failed_dates.return_value = []
    mock.ingestion_log_store.get_ingested_dates.return_value = []

    return mock


@pytest.fixture
def patch_datahub(mock_datahub: MagicMock) -> MagicMock:
    """返回 Mock DataHub 对象（不进行全局 patch）.

    注意：此 fixture 不再全局 patch DataHub 类，
    因为会与 dishka 依赖注入容器冲突。

    集成测试应使用真实的 DataHub（通过 create_ingestion_context），
    单元测试可自行 mock 需要的组件。

    使用方式（单元测试）：
        def test_something(patch_datahub):
            # 使用 mock 对象进行测试
            assert patch_datahub.metadata.is_trading_day() is True

    Args:
        mock_datahub: 独立的 Mock DataHub 对象

    Returns:
        MagicMock: mock_datahub 对象
    """
    return mock_datahub
