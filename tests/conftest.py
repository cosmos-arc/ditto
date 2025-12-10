"""Global pytest configuration and fixtures for Ditto trading system."""

import random
import sys
import tempfile
from collections.abc import Generator
from datetime import datetime
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import polars as pl
import pytest
from _pytest.fixtures import SubRequest
from _pytest.nodes import Item

# Add src directories to Python path for editable imports
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root / "packages" / "core" / "src"))
sys.path.insert(0, str(project_root / "packages" / "foundation" / "src"))
sys.path.insert(0, str(project_root / "apps" / "server" / "src"))


# Global test data fixtures
@pytest.fixture
def sample_price_data(request: SubRequest) -> pl.DataFrame:
    """
    Provide sample daily price data for testing.

    Returns:
        pl.DataFrame: Sample price data with OHLCV

    """
    data = {
        "symbol": ["510300.SH", "510300.SH", "510300.SH", "510300.SH", "510300.SH"],
        "trade_date": [
            "2024-01-02",
            "2024-01-03",
            "2024-01-04",
            "2024-01-05",
            "2024-01-08",
        ],
        "open_price": [3.500, 3.520, 3.510, 3.530, 3.540],
        "high_price": [3.550, 3.530, 3.525, 3.550, 3.560],
        "low_price": [3.480, 3.500, 3.500, 3.520, 3.530],
        "close_price": [3.520, 3.510, 3.520, 3.540, 3.550],
        "volume": [1000000, 1200000, 900000, 1100000, 1300000],
        "amount": [3520000.0, 4212000.0, 3168000.0, 3794000.0, 4615000.0],
        "knowledge_date": [
            "2024-01-02",
            "2024-01-03",
            "2024-01-04",
            "2024-01-05",
            "2024-01-08",
        ],
    }
    return pl.DataFrame(data)


@pytest.fixture
def sample_etf_data() -> pl.DataFrame:
    """
    Provide sample ETF data for testing.

    Returns:
        pl.DataFrame: Sample ETF list data

    """
    data = {
        "symbol": ["510300.SH", "510500.SH", "159919.SZ", "512100.SH", "516010.SH"],
        "name": ["沪深300ETF", "中证500ETF", "沪深300ETF", "中证1000ETF", "游戏ETF"],
        "fund_manager": ["华泰柏瑞", "南方基金", "嘉实基金", "华夏基金", "华夏基金"],
        "tracking_index": [
            "沪深300指数",
            "中证500指数",
            "沪深300指数",
            "中证1000指数",
            "动漫游戏指数",
        ],
        "establishment_date": [
            "2012-04-26",
            "2013-02-25",
            "2012-05-07",
            "2016-10-21",
            "2021-02-24",
        ],
    }
    return pl.DataFrame(data)


@pytest.fixture
def sample_adjustment_factor_data() -> pl.DataFrame:
    """
    Provide sample adjustment factor data for testing.

    Returns:
        pl.DataFrame: Sample adjustment factor data

    """
    data = {
        "symbol": ["510300.SH", "510300.SH", "510300.SH"],
        "ex_date": ["2024-03-15", "2024-06-15", "2024-09-15"],
        "adj_factor": [1.05, 1.08, 1.12],
        "adj_type": ["cumulative", "cumulative", "cumulative"],
        "knowledge_date": ["2024-03-15", "2024-06-15", "2024-09-15"],
    }
    return pl.DataFrame(data)


@pytest.fixture
def temp_dir() -> Generator[Path, None, None]:
    """
    Provide a temporary directory for testing.

    Yields:
        Path: Temporary directory path

    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        yield Path(tmp_dir)


@pytest.fixture
def mock_current_time() -> Generator[None, None, None]:
    """Mock current time for consistent testing."""
    fixed_time = datetime(2024, 1, 8, 15, 0, 0)
    with patch("datetime.datetime") as mock_datetime:
        mock_datetime.now.return_value = fixed_time
        mock_datetime.side_effect = lambda *args, **kw: datetime(*args, **kw)
        yield


@pytest.fixture
def mock_tushare_api() -> Generator[MagicMock, None, None]:
    """
    Mock Tushare API for testing.

    Yields:
        MagicMock: Mocked Tushare API

    """
    mock_pro = MagicMock()

    # Mock trade_cal response
    mock_pro.trade_cal.return_value = pl.DataFrame(
        {
            "exchange": ["SSE"],
            "cal_date": ["20240101"],
            "is_open": [0],
        }
    ).to_pandas()

    # Mock fund_basic response
    mock_etf_data = {
        "ts_code": ["510300.SH", "510500.SH"],
        "name": ["沪深300ETF", "中证500ETF"],
        "management": ["华泰柏瑞", "南方基金"],
        "benchmark": ["沪深300指数", "中证500指数"],
        "establish_date": ["20120426", "20130225"],
    }
    mock_pro.fund_basic.return_value = pl.DataFrame(mock_etf_data).to_pandas()

    # Mock daily response
    mock_daily_data = {
        "ts_code": ["510300.SH", "510300.SH"],
        "trade_date": ["20240102", "20240103"],
        "open": [3.500, 3.520],
        "high": [3.550, 3.530],
        "low": [3.480, 3.500],
        "close": [3.520, 3.510],
        "vol": [1000000, 1200000],
        "amount": [3520000.0, 4212000.0],
    }
    mock_pro.daily.return_value = pl.DataFrame(mock_daily_data).to_pandas()

    # Mock adj_factor response
    mock_adj_data = {
        "ts_code": ["510300.SH"],
        "trade_date": ["20240315"],
        "adj_factor": [1.05],
    }
    mock_pro.adj_factor.return_value = pl.DataFrame(mock_adj_data).to_pandas()

    with patch("tushare.pro_api", return_value=mock_pro), patch("tushare.set_token"):
        yield mock_pro


@pytest.fixture
def mock_akshare_api() -> Generator[dict[str, Any], None, None]:
    """
    Mock AkShare API for testing.

    Yields:
        dict: Mocked AkShare API functions

    """
    mock_ak = MagicMock()

    # Mock fund_etf_basic response
    mock_etf_data = pl.DataFrame(
        {
            "基金代码": ["510300", "510500"],
            "基金简称": ["沪深300ETF", "中证500ETF"],
            "基金管理人": ["华泰柏瑞", "南方基金"],
            "业绩比较基准": ["沪深300指数", "中证500指数"],
            "成立日期": ["2012-04-26", "2013-02-25"],
        }
    )

    # Mock stock_zh_a_hist response
    mock_daily_data = pl.DataFrame(
        {
            "日期": ["2024-01-02", "2024-01-03"],
            "开盘": [3.500, 3.520],
            "最高": [3.550, 3.530],
            "最低": [3.480, 3.500],
            "收盘": [3.520, 3.510],
            "成交量": [1000000, 1200000],
            "成交额": [3520000.0, 4212000.0],
        }
    )

    def mock_fund_etf_basic(**kwargs: Any) -> Any:
        return mock_etf_data.to_pandas()

    def mock_stock_zh_a_hist(**kwargs: Any) -> Any:
        return mock_daily_data.to_pandas()

    mock_ak.fund_etf_basic.side_effect = mock_fund_etf_basic
    mock_ak.stock_zh_a_hist.side_effect = mock_stock_zh_a_hist

    with patch("ditto_core.data.datasources.akshare.ak", mock_ak):
        yield mock_ak


@pytest.fixture(autouse=True)
def fixed_seed() -> None:
    """
    Set fixed random seed for reproducible tests.

    This fixture is automatically used for all tests.
    """
    random.seed(42)
    # Note: We don't set numpy/polars seeds here as they might not be imported


def pytest_configure(config: Any) -> None:
    """Configure pytest with custom markers."""
    config.addinivalue_line("markers", "unit: Mark test as a unit test")
    config.addinivalue_line("markers", "integration: Mark test as an integration test")
    config.addinivalue_line("markers", "e2e: Mark test as an end-to-end test")
    config.addinivalue_line(
        "markers", "slow: Mark test as slow running (skip with -m 'not slow')"
    )
    config.addinivalue_line("markers", "smoke: Mark test as a smoke test")
    config.addinivalue_line(
        "markers", "benchmark: Mark test as a performance benchmark test"
    )
    config.addinivalue_line("markers", "network: Mark test as requiring network access")
    config.addinivalue_line("markers", "database: Mark test as requiring database")


def pytest_collection_modifyitems(config: Any, items: list[Item]) -> None:
    """
    Automatically mark tests based on their location and naming.

    Args:
        config: Pytest config object
        items: List of test items to be modified

    """
    for item in items:
        # Normalize path separators for cross-platform compatibility
        path_str = str(item.fspath).replace("\\", "/")

        # Mark based on file location
        if "/tests/unit/" in path_str or path_str.endswith("/tests/unit"):
            item.add_marker(pytest.mark.unit)
        elif "/tests/integration/" in path_str or path_str.endswith(
            "/tests/integration"
        ):
            item.add_marker(pytest.mark.integration)
        elif "/tests/e2e/" in path_str or path_str.endswith("/tests/e2e"):
            item.add_marker(pytest.mark.e2e)
        elif "/tests/perf/" in path_str or path_str.endswith("/tests/perf"):
            item.add_marker(pytest.mark.benchmark)

        # Mark slow tests based on naming convention
        if "slow_" in item.name or "_slow" in item.name:
            item.add_marker(pytest.mark.slow)

        # Mark tests that might need network access
        if (
            "test_tushare" in item.name
            or "test_akshare" in item.name
            or "network" in item.name
        ):
            item.add_marker(pytest.mark.network)

        # Mark database tests
        if (
            "database" in item.name
            or "adapter" in item.name
            or "duckdb" in item.name
            or "sqlite" in item.name
        ):
            item.add_marker(pytest.mark.database)
