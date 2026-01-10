"""pytest配置文件."""

import os
import sqlite3
from collections.abc import Generator
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

import duckdb
import pytest
from ditto_foundation.config import Settings


class DatabaseManager:
    """数据库连接池管理器。"""

    _duckdb_conn: duckdb.DuckDBPyConnection | None

    def __init__(self) -> None:
        self._duckdb_conn = None

    def get_duckdb_conn(self) -> duckdb.DuckDBPyConnection:
        """获取 DuckDB 连接。

        如果连接不存在，则创建新的连接并初始化表结构。
        连接使用 :memory: 数据库，在测试会话中复用。

        Returns:
            DuckDB 连接对象
        """
        if self._duckdb_conn is None:
            self._duckdb_conn = duckdb.connect(":memory:")
            self._init_duckdb_tables()
        return self._duckdb_conn

    def _init_duckdb_tables(self) -> None:
        """初始化 DuckDB 表结构。"""
        conn = self._duckdb_conn
        conn.execute("""
            CREATE TABLE IF NOT EXISTS etf_list (
                symbol VARCHAR, name VARCHAR, market VARCHAR,
                category VARCHAR, establish_date DATE, fund_manager VARCHAR,
                tracking_index VARCHAR, knowledge_date DATE
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS daily_price_raw (
                symbol VARCHAR, date DATE, open_price DOUBLE, high_price DOUBLE,
                low_price DOUBLE, close_price DOUBLE, volume BIGINT,
                amount DOUBLE, knowledge_date DATE
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS daily_price_adjusted (
                symbol VARCHAR, date DATE, open DOUBLE, high DOUBLE,
                low DOUBLE, close DOUBLE, volume BIGINT, knowledge_date DATE
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS adjustment_factors (
                symbol VARCHAR, ex_date DATE, adj_factor DOUBLE, knowledge_date DATE
            )
        """)

    def clean_duckdb(self) -> None:
        """清理数据。

        删除所有表中的数据，但保留表结构。
        如果连接不存在，则不执行任何操作。
        """
        if self._duckdb_conn:
            self._duckdb_conn.execute("DELETE FROM etf_list")
            self._duckdb_conn.execute("DELETE FROM daily_price_raw")
            self._duckdb_conn.execute("DELETE FROM daily_price_adjusted")
            self._duckdb_conn.execute("DELETE FROM adjustment_factors")


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


@pytest.fixture
def temp_dir() -> Generator[Path, None, None]:
    """临时目录fixture."""
    with TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def test_settings(temp_dir: Path) -> Settings:
    """测试配置fixture."""
    # 通过环境变量设置数据库路径
    os.environ["DB_DUCKDB_PATH"] = str(temp_dir / "test.duckdb")
    os.environ["DB_SQLITE_PATH"] = str(temp_dir / "test.sqlite")
    os.environ["TUSHARE_TOKEN"] = "test_token"
    os.environ["DITTO_ENV"] = "testing"

    settings = Settings()

    # 清理环境变量
    del os.environ["DB_DUCKDB_PATH"]
    del os.environ["DB_SQLITE_PATH"]
    del os.environ["TUSHARE_TOKEN"]
    del os.environ["DITTO_ENV"]

    return settings


@pytest.fixture(scope="session")
def test_settings_session() -> Generator[Settings, None, None]:
    """Session 级别的 Settings，避免重复初始化."""
    with TemporaryDirectory() as tmpdir:
        temp_path = Path(tmpdir)

        os.environ["DB_DUCKDB_PATH"] = str(temp_path / "test.duckdb")
        os.environ["DB_SQLITE_PATH"] = str(temp_path / "test.sqlite")
        os.environ["TUSHARE_TOKEN"] = "test_token"
        os.environ["DITTO_ENV"] = "testing"

        settings = Settings()

        yield settings

        # 清理环境变量
        del os.environ["DB_DUCKDB_PATH"]
        del os.environ["DB_SQLITE_PATH"]
        del os.environ["TUSHARE_TOKEN"]
        del os.environ["DITTO_ENV"]


@pytest.fixture(scope="session")
def db_manager() -> Generator[DatabaseManager, None, None]:
    """Session 级别的数据库管理器."""
    manager = DatabaseManager()
    yield manager
    if manager._duckdb_conn:
        manager._duckdb_conn.close()


@pytest.fixture
def clean_duckdb(db_manager: DatabaseManager) -> duckdb.DuckDBPyConnection:
    """提供清理后的连接."""
    db_manager.clean_duckdb()
    return db_manager.get_duckdb_conn()


@pytest.fixture
def sqlite_conn(
    test_settings_session: Settings,
) -> Generator[sqlite3.Connection, None, None]:
    """SQLite连接fixture."""
    conn = sqlite3.connect(str(test_settings_session.database.sqlite_path))

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
    from ditto_foundation import Mode, init

    init(mode=Mode.TESTING)


@pytest.fixture
def obs_assertions() -> None:
    """断言模式 - 可验证, 内存记录."""
    from ditto_foundation import Mode, init

    init(mode=Mode.TESTING_WITH_ASSERTIONS)
