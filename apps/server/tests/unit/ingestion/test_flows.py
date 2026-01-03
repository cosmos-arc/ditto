"""Tests for ingestion flows (legacy implementation).

.. deprecated::
    These tests use the old flow implementation (daily_ingest_flow).
    The old flow has been replaced by the new implementation (flows/daily.py).
    See: apps/server/src/ditto_server/ingestion/flows/daily.py
    for the new implementation.
"""

# ruff: noqa: E402  # 测试文件允许 warnings.filterwarnings 在 import 之前

import warnings

# Suppress deprecation warnings when testing legacy code
warnings.filterwarnings("ignore", category=DeprecationWarning)

from unittest.mock import patch

import pytest
from ditto_foundation.observability import Mode, init, reset_for_testing
from ditto_server.ingestion.flows.daily_ingest import daily_ingest_flow


@pytest.fixture(autouse=True)
def setup_observability():
    """Initialize observability for metrics testing."""
    reset_for_testing()
    init(mode=Mode.TESTING_WITH_ASSERTIONS, force=True)
    yield
    reset_for_testing()


@patch("ditto_server.ingestion.flows.daily_ingest.ingest_etf_bars")
def test_daily_ingest_flow_success(mock_ingest):
    """Test successful daily ingestion flow."""
    # Mock the task to return success
    mock_ingest.return_value = {
        "trade_date": "2024-01-02",
        "source": "tushare",
        "rows_fetched": 2,
        "rows_written": 2,
        "new_securities_registered": 0,
        "skipped_securities": 0,
        "failed_checks": 0,
        "status": "success",
    }

    result = daily_ingest_flow("2024-01-02")

    assert result["status"] == "success"
    assert result["trade_date"] == "2024-01-02"
    assert result["source"] == "tushare"
    assert "tasks" in result
    assert "etf_bars" in result["tasks"]  # type: ignore[operator]
    assert result["tasks"]["etf_bars"]["status"] == "success"  # type: ignore[index]


@patch("ditto_server.ingestion.flows.daily_ingest.ingest_etf_bars")
def test_daily_ingest_flow_with_warnings(mock_ingest):
    """Test flow when task returns warning status."""
    mock_ingest.return_value = {
        "trade_date": "2024-01-02",
        "source": "tushare",
        "rows_fetched": 2,
        "rows_written": 1,
        "new_securities_registered": 1,
        "skipped_securities": 1,
        "failed_checks": 0,
        "status": "warning",
    }

    result = daily_ingest_flow("2024-01-02")

    assert result["status"] == "warning"
    assert result["tasks"]["etf_bars"]["skipped_securities"] == 1  # type: ignore[index]


@patch("ditto_server.ingestion.flows.daily_ingest.ingest_etf_bars")
def test_daily_ingest_flow_failure(mock_ingest):
    """Test flow when task returns no_data status."""
    mock_ingest.return_value = {
        "trade_date": "2024-01-02",
        "source": "tushare",
        "rows_fetched": 0,
        "rows_written": 0,
        "new_securities_registered": 0,
        "skipped_securities": 0,
        "failed_checks": 0,
        "status": "no_data",
    }

    result = daily_ingest_flow("2024-01-02")

    assert result["status"] == "failed"


@patch("ditto_server.ingestion.flows.daily_ingest.ingest_etf_bars")
def test_daily_ingest_flow_custom_params(mock_ingest):
    """Test flow with custom parameters."""
    mock_ingest.return_value = {
        "trade_date": "2024-01-03",
        "source": "custom",
        "rows_fetched": 5,
        "rows_written": 5,
        "new_securities_registered": 0,
        "skipped_securities": 0,
        "failed_checks": 0,
        "status": "success",
    }

    result = daily_ingest_flow(
        trade_date="2024-01-03",
        source="custom",
        data_root="/custom/path",
    )

    assert result["status"] == "success"
    assert result["source"] == "custom"

    # Verify task was called with correct parameters
    mock_ingest.assert_called_once_with(
        trade_date="2024-01-03",
        source="custom",
        data_root="/custom/path",
    )
