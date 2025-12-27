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


@pytest.fixture
def duckdb_conn(
    test_settings: Settings,
) -> Generator[duckdb.DuckDBPyConnection, None, None]:
    """DuckDB连接fixture."""
    conn = duckdb.connect(str(test_settings.database.duckdb_path))

    # 初始化表结构
    conn.execute("""
        CREATE TABLE IF NOT EXISTS etf_list (
            symbol VARCHAR,
            name VARCHAR,
            market VARCHAR,
            category VARCHAR,
            establish_date DATE,
            fund_manager VARCHAR,
            tracking_index VARCHAR,
            knowledge_date DATE
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS daily_price_raw (
            symbol VARCHAR,
            date DATE,
            open_price DOUBLE,
            high_price DOUBLE,
            low_price DOUBLE,
            close_price DOUBLE,
            volume BIGINT,
            amount DOUBLE,
            knowledge_date DATE
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS daily_price_adjusted (
            symbol VARCHAR,
            date DATE,
            open DOUBLE,
            high DOUBLE,
            low DOUBLE,
            close DOUBLE,
            volume BIGINT,
            knowledge_date DATE
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS adjustment_factors (
            symbol VARCHAR,
            ex_date DATE,
            adj_factor DOUBLE,
            knowledge_date DATE
        )
    """)

    yield conn

    conn.close()


@pytest.fixture
def sqlite_conn(test_settings: Settings) -> Generator[sqlite3.Connection, None, None]:
    """SQLite连接fixture."""
    conn = sqlite3.connect(str(test_settings.database.sqlite_path))

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


@pytest.fixture
def populated_databases(
    duckdb_conn: duckdb.DuckDBPyConnection,
    sqlite_conn: sqlite3.Connection,
    sample_etf_data: list[dict[str, Any]],
    sample_daily_data: list[dict[str, Any]],
) -> tuple[duckdb.DuckDBPyConnection, sqlite3.Connection]:
    """填充测试数据的数据库."""
    # 插入ETF数据
    duckdb_conn.executemany(
        """
        INSERT INTO etf_list (
            symbol, name, market, category, establish_date,
            fund_manager, tracking_index, knowledge_date
        ) VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?
        )
        """,
        [
            (
                d["symbol"],
                d["name"],
                d["market"],
                d["category"],
                d["establish_date"],
                d["fund_manager"],
                d["tracking_index"],
                d["knowledge_date"],
            )
            for d in sample_etf_data
        ],
    )

    # 插入日线数据
    duckdb_conn.executemany(
        """
        INSERT INTO daily_price_adjusted (
            symbol, date, open, high, low, close, volume, knowledge_date
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                d["symbol"],
                d["date"],
                d["open"],
                d["high"],
                d["low"],
                d["close"],
                d["volume"],
                d["knowledge_date"],
            )
            for d in sample_daily_data
        ],
    )

    # 插入交易日历数据
    trading_days = []
    for i in range(31):
        date = f"2024-01-{i + 1:02d}"
        trading_days.append(
            {
                "date": date,
                "is_trading_day": i % 7 not in [5, 6],  # 周末不交易
                "knowledge_date": "2024-01-01",
            }
        )

    sqlite_conn.executemany(
        """
        INSERT INTO trading_calendar (date, is_trading_day, knowledge_date)
        VALUES (?, ?, ?)
        """,
        [(d["date"], d["is_trading_day"], d["knowledge_date"]) for d in trading_days],
    )

    return duckdb_conn, sqlite_conn


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
