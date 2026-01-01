"""Tests for ingestion tasks.

.. deprecated::
    These tests use the old ingestion interface (IncrementalMode.QUICK/PRECISE).
    After Phase 0.4 (Source layer refactoring) is complete, these tests should be
    updated to use the new `ingest_date()` interface with `force` parameter.

    See: C:\\Users\\36486\\.claude\\plans\\humming-skipping-parrot.md
"""

from datetime import date
from unittest.mock import Mock, patch

import polars as pl
import pytest
from ditto_foundation.observability import Mode, init, reset_for_testing
from ditto_server.ingestion.tasks.bars import ingest_etf_bars


@pytest.fixture(autouse=True)
def setup_observability():
    """Initialize observability for metrics testing."""
    reset_for_testing()
    init(mode=Mode.TESTING_WITH_ASSERTIONS, force=True)
    yield
    reset_for_testing()


@pytest.fixture
def mock_hub():
    """Create a mock DataHub."""
    hub = Mock()

    # Mock sources accessor - create a mock source object
    mock_source = Mock()
    hub.sources.get.return_value = mock_source
    hub.sources.tushare = mock_source  # For direct access

    # Mock securities repository
    hub.securities.resolve_identifiers_batch.return_value = {}
    hub.securities.register.return_value = 200000001

    # Mock bars repository - dynamically return actual row count
    def mock_write(df, **kwargs):
        mock_result = Mock()
        mock_result.rows_written = len(df)
        mock_result.failed_checks = []
        return mock_result

    hub.bars.write = mock_write

    return hub


def test_ingest_etf_bars_success(mock_hub):
    """Test successful ETF bars ingestion."""
    # Mock fetch - return data with 2 rows
    mock_df = pl.DataFrame(
        {
            "src_code": ["510300.SH", "510500.SH"],
            "trade_date": [date(2024, 1, 2), date(2024, 1, 2)],
            "open": [4.0, 4.5],
            "high": [4.1, 4.6],
            "low": [3.9, 4.4],
            "close": [4.05, 4.55],
            "pre_close": [4.0, 4.5],
            "volume": [1000000, 2000000],
            "amount": [4050000, 9100000],
            "pct_change": [1.25, 1.11],
        }
    )

    # Mock SID resolution - both securities already exist
    mock_hub.sources.tushare.fetch_etf_daily.return_value = mock_df
    mock_hub.sources.tushare.fetch_etf_basic.return_value = pl.DataFrame(
        schema=["src_code", "symbol", "name", "exchange", "list_date"]
    )
    mock_hub.securities.resolve_identifiers_batch.return_value = {
        "510300.SH": 200000001,
        "510500.SH": 200000002,
    }

    with patch("ditto_server.ingestion.tasks.bars.DataHub", return_value=mock_hub):
        result = ingest_etf_bars.fn("2024-01-02", "tushare", "data")

    assert result["status"] == "success"
    assert result["rows_fetched"] == 2
    assert result["rows_written"] == 2
    assert result["new_securities_registered"] == 0
    assert result["skipped_securities"] == 0
    assert result["failed_checks"] == 0


def test_ingest_etf_bars_with_new_securities(mock_hub):
    """Test ETF bars ingestion with new securities registration."""
    # Mock fetch
    mock_df = pl.DataFrame(
        {
            "src_code": ["510300.SH"],
            "trade_date": [date(2024, 1, 2)],
            "open": [4.0],
            "high": [4.1],
            "low": [3.9],
            "close": [4.05],
            "pre_close": [4.0],
            "volume": [1000000],
            "amount": [4050000],
            "pct_change": [1.25],
        }
    )

    # Mock basic ETF info
    mock_basic_df = pl.DataFrame(
        {
            "src_code": ["510300.SH"],
            "symbol": ["510300"],
            "name": ["CSI 300 ETF"],
            "exchange": ["SSE"],
            "list_date": [date(2012, 4, 5)],
        }
    )

    # No existing SID mapping
    mock_hub.sources.tushare.fetch_etf_daily.return_value = mock_df
    mock_hub.sources.tushare.fetch_etf_basic.return_value = mock_basic_df
    mock_hub.securities.resolve_identifiers_batch.return_value = {}
    mock_hub.securities.register.return_value = 200000001

    with patch("ditto_server.ingestion.tasks.bars.DataHub", return_value=mock_hub):
        result = ingest_etf_bars.fn("2024-01-02", "tushare", "data")

    assert result["status"] == "success"
    assert result["new_securities_registered"] == 1
    assert result["rows_written"] == 1


def test_ingest_etf_bars_empty_data(mock_hub):
    """Test ETF bars ingestion when source returns no data."""
    mock_hub.sources.tushare.fetch_etf_daily.return_value = pl.DataFrame()

    with patch("ditto_server.ingestion.tasks.bars.DataHub", return_value=mock_hub):
        result = ingest_etf_bars.fn("2024-01-02", "tushare", "data")

    assert result["status"] == "no_data"
    assert result["rows_fetched"] == 0
    assert result["rows_written"] == 0


def test_ingest_etf_bars_partial_failure(mock_hub):
    """Test ETF bars ingestion with registration failures."""
    # Mock fetch
    mock_df = pl.DataFrame(
        {
            "src_code": ["510300.SH"],
            "trade_date": [date(2024, 1, 2)],
            "open": [4.0],
            "high": [4.1],
            "low": [3.9],
            "close": [4.05],
            "pre_close": [4.0],
            "volume": [1000000],
            "amount": [4050000],
            "pct_change": [1.25],
        }
    )

    mock_basic_df = pl.DataFrame(
        {
            "src_code": ["510300.SH"],
            "symbol": ["510300"],
            "name": ["CSI 300 ETF"],
            "exchange": ["SSE"],
            "list_date": [date(2012, 4, 5)],
        }
    )

    mock_hub.sources.tushare.fetch_etf_daily.return_value = mock_df
    mock_hub.sources.tushare.fetch_etf_basic.return_value = mock_basic_df
    mock_hub.securities.resolve_identifiers_batch.return_value = {}

    # Mock register to raise exception
    mock_hub.securities.register.side_effect = Exception("Registration failed")

    with patch("ditto_server.ingestion.tasks.bars.DataHub", return_value=mock_hub):
        result = ingest_etf_bars.fn("2024-01-02", "tushare", "data")

    assert result["status"] == "warning"  # Has skipped securities
    assert result["skipped_securities"] == 1
    assert len(result["skipped_list"]) == 1  # type: ignore[arg-type]
