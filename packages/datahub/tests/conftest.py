"""Pytest configuration for datahub tests."""

from collections.abc import Generator
from datetime import date
from pathlib import Path
from typing import Any

import polars as pl
import pytest
from ditto_datahub.stores.sqlite_client import SQLiteClient
from ditto_foundation import SQLitePool, init
from ditto_foundation.config.environment import Environment
from ditto_foundation.observability.config import ObservabilityConfig


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """
    Auto-mark tests based on their directory location.

    - tests/unit/ -> unit
    - tests/integration/ -> integration
    Only special cases need manual markers.
    """
    for item in items:
        try:
            # Get the relative path from the tests directory
            rel_path = item.path.relative_to(Path(__file__).parent)

            # Mark based on directory
            if "integration" in str(rel_path):
                item.add_marker(pytest.mark.integration)
            elif "unit" in str(rel_path):
                item.add_marker(pytest.mark.unit)
        except ValueError:
            # Item is not under this conftest's directory, skip
            # It will be handled by its own package's conftest
            pass


@pytest.fixture(autouse=True)
def init_observability() -> None:
    """Initialize observability in testing mode for all tests."""
    config = ObservabilityConfig(
        environment=Environment.TESTING,
        pytest_running=True,
        assertions_enabled=False,
        verbose_logging=False,
        tracing_enabled=False,
        metrics_enabled=False,
    )
    init(config, force=True)
    # Cleanup is handled by reset_for_testing if needed


@pytest.fixture(scope="session")
def sqlite_schema_path() -> Path:
    """
    获取数据库 schema 文件路径。

    Session 级别 fixture，在整个测试会话中只计算一次。

    Returns:
        Path: 指向 schema.sql 文件的路径
    """
    schema_file = (
        Path(__file__).parent.parent
        / "src"
        / "ditto_datahub"
        / "scripts"
        / "schema.sql"
    )
    if not schema_file.exists():
        raise FileNotFoundError(f"Schema file not found: {schema_file}")
    return schema_file


@pytest.fixture
def sqlite_pool(sqlite_schema_path: Path) -> SQLitePool:
    """
    创建已初始化的 SQLite 连接池。

    每个测试函数使用独立的内存数据库，确保测试隔离。

    Args:
        sqlite_schema_path: Schema 文件路径（从 session fixture 注入）

    Returns:
        SQLitePool: 已初始化表结构的连接池
    """
    pool = SQLitePool(":memory:", schema_path=sqlite_schema_path)
    pool.init_schema()
    return pool


@pytest.fixture
def sqlite_client(sqlite_pool: SQLitePool) -> SQLiteClient:
    """
    创建 SQLite 客户端。

    Args:
        sqlite_pool: 已初始化的连接池

    Returns:
        SQLiteClient: SQL 执行客户端
    """
    return SQLiteClient(sqlite_pool)


@pytest.fixture
def fake_time(monkeypatch: pytest.MonkeyPatch) -> Generator[None, None, None]:
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

    return


# ============ Shared test data fixtures ============


@pytest.fixture
def sample_adj_factor_df() -> pl.DataFrame:
    """
    Create sample adjustment factor data for testing.

    Returns:
        DataFrame with sid, trade_date, and adj_factor columns.
    """
    data: dict[str, list[Any]] = {
        "sid": [1000001, 1000001, 1000001, 1000002],
        "trade_date": [
            date(2024, 1, 2),
            date(2024, 1, 3),
            date(2024, 1, 4),
            date(2024, 1, 2),
        ],
        "adj_factor": [1.0, 1.0, 0.95, 1.0],
    }
    return pl.DataFrame(data)


@pytest.fixture
def sample_stock_status_df() -> pl.DataFrame:
    """
    Create sample stock status data for testing.

    Returns:
        DataFrame with stock status columns including is_suspended, is_st, etc.
    """
    data: dict[str, list[Any]] = {
        "sid": [100000001, 100000001, 100000001, 100000002],
        "trade_date": [
            date(2024, 1, 2),
            date(2024, 1, 3),
            date(2024, 1, 4),
            date(2024, 1, 2),
        ],
        "is_suspended": [False, False, True, False],
        "suspend_timing": [None, None, "09:30-10:00", None],
        "is_st": [False, False, False, True],
        "st_type": [None, None, None, "ST"],
        "list_status": ["L", "L", "L", "L"],
        "source": ["tushare", "tushare", "tushare", "tushare"],
        "src_code": ["000001.SZ", "000001.SZ", "000001.SZ", "000002.SZ"],
    }
    return pl.DataFrame(data)


@pytest.fixture
def sample_stock_daily_df() -> pl.DataFrame:
    """
    Create sample stock daily OHLC data for testing.

    Returns:
        DataFrame with sid, trade_date, open, high, low, close, volume, amount.
    """
    data: dict[str, list[Any]] = {
        "sid": [1_000_001, 1_000_001, 1_000_001, 1_000_002],
        "trade_date": [
            date(2024, 1, 1),
            date(2024, 1, 2),
            date(2024, 1, 3),
            date(2024, 1, 2),
        ],
        "open": [10.0, 10.5, 11.0, 20.0],
        "high": [10.5, 11.0, 11.5, 20.5],
        "low": [9.5, 10.0, 10.5, 19.5],
        "close": [10.0, 10.5, 11.0, 20.0],
        "pre_close": [9.8, 10.0, 10.5, 19.8],
        "volume": [1000, 1500, 2000, 3000],
        "amount": [10000.0, 15000.0, 20000.0, 60000.0],
    }
    return pl.DataFrame(data)


@pytest.fixture
def sample_calendar_df() -> pl.DataFrame:
    """
    Create sample calendar data for testing.

    Returns:
        DataFrame with trade_date and is_open columns.
    """
    data: dict[str, list[Any]] = {
        "trade_date": [
            date(2024, 1, 1),
            date(2024, 1, 2),
            date(2024, 1, 3),
            date(2024, 1, 6),
        ],
        "is_open": [False, True, True, False],  # Jan 1 and Jan 6 (Sat) are closed
    }
    return pl.DataFrame(data)


@pytest.fixture
def sample_etf_daily_df() -> pl.DataFrame:
    """
    Create sample ETF daily OHLC data for testing.

    Returns:
        DataFrame with sid, trade_date, open, high, low, close, volume, amount.
    """
    data: dict[str, list[Any]] = {
        "sid": [2_000_001, 2_000_001, 2_000_001],
        "trade_date": [
            date(2024, 1, 1),
            date(2024, 1, 2),
            date(2024, 1, 3),
        ],
        "open": [3.5, 3.6, 3.7],
        "high": [3.6, 3.7, 3.8],
        "low": [3.4, 3.5, 3.6],
        "close": [3.5, 3.6, 3.7],
        "pre_close": [3.45, 3.5, 3.6],
        "volume": [5000, 6000, 7000],
        "amount": [17500.0, 21600.0, 25900.0],
    }
    return pl.DataFrame(data)


@pytest.fixture
def data_root(tmp_path: Path) -> Path:
    """
    Create temporary data root directory for testing.

    Args:
        tmp_path: pytest's temporary path fixture

    Returns:
        Path: temporary data directory
    """
    return tmp_path / "data"
