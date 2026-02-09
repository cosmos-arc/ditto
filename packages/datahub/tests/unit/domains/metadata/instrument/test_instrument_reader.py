"""Tests for InstrumentReader."""

from __future__ import annotations

from unittest.mock import Mock

import pytest
from ditto_datahub.stores.metadata.instrument.instrument_reader import InstrumentReader


@pytest.fixture
def mock_client() -> Mock:
    """Create mock SQLite client."""
    client = Mock()
    client.fetchone = Mock(return_value=None)
    client.fetchall = Mock(return_value=[])
    return client


@pytest.fixture
def mock_cache() -> Mock:
    """Create mock cache manager."""
    cache = Mock()
    cache.get = Mock(return_value=None)
    cache.set = Mock()
    cache.invalidate = Mock()
    cache.invalidate_pattern = Mock(return_value=0)
    return cache


@pytest.fixture
def reader(mock_client: Mock, mock_cache: Mock) -> InstrumentReader:
    """Create InstrumentReader instance."""
    return InstrumentReader(mock_client, mock_cache)


class TestInstrumentReader:
    """Test suite for InstrumentReader."""

    def test_resolve_instrument_id_found(self, reader: InstrumentReader) -> None:
        """Test resolve_instrument_id returns instrument_id."""
        # Setup mock to return a result
        reader._client.fetchone = Mock(return_value={"instrument_id": 100000001})

        result = reader.resolve_instrument_id("600000.SH", "tushare")

        assert result == 100000001

    def test_resolve_instrument_id_not_found(self, reader: InstrumentReader) -> None:
        """Test resolve_instrument_id returns None for not found."""
        reader._client.fetchone = Mock(return_value=None)

        result = reader.resolve_instrument_id("999999.SH", "tushare")

        assert result is None

    def test_resolve_instrument_id_with_cache_hit(
        self,
        reader: InstrumentReader,
    ) -> None:
        """Test resolve_instrument_id returns cached value."""
        reader._cache.get = Mock(return_value=100000001)

        result = reader.resolve_instrument_id("600000.SH", "tushare")

        assert result == 100000001
        # Should not query database
        reader._client.fetchone.assert_not_called()

    def test_resolve_instrument_id_with_asof(self, reader: InstrumentReader) -> None:
        """Test resolve_instrument_id with PIT query."""
        reader._client.fetchone = Mock(return_value={"instrument_id": 100000001})

        result = reader.resolve_instrument_id("600000.SH", "tushare", asof="2024-01-01")

        assert result == 100000001
        # Verify SQL includes PIT conditions
        call_args = reader._client.fetchone.call_args
        sql = call_args[0][0]
        assert "effective_from <= ?" in sql
        assert "(effective_to IS NULL OR effective_to > ?)" in sql

    def test_resolve_instrument_ids_batch(self, reader: InstrumentReader) -> None:
        """Test batch resolution."""
        rows = [
            {"source_ticker": "600000.SH", "instrument_id": 100000001},
            {"source_ticker": "600004.SH", "instrument_id": 100000002},
        ]
        reader._client.fetchall = Mock(return_value=rows)

        result = reader.resolve_instrument_ids_batch(
            ["600000.SH", "600004.SH"], "tushare"
        )

        assert len(result) == 2
        assert result["600000.SH"] == 100000001
        assert result["600004.SH"] == 100000002

    def test_resolve_instrument_ids_batch_empty(self, reader: InstrumentReader) -> None:
        """Test batch resolution with empty list."""
        result = reader.resolve_instrument_ids_batch([], "tushare")

        assert result == {}

    def test_get_source_ticker(self, reader: InstrumentReader) -> None:
        """Test get_source_ticker reverse lookup."""
        reader._client.fetchone = Mock(return_value={"source_ticker": "600000.SH"})

        result = reader.get_source_ticker(100000001, "tushare")

        assert result == "600000.SH"

    def test_get_source_ticker_not_found(self, reader: InstrumentReader) -> None:
        """Test get_source_ticker returns None."""
        reader._client.fetchone = Mock(return_value=None)

        result = reader.get_source_ticker(999, "tushare")

        assert result is None

    def test_get_source_ticker_with_asof(self, reader: InstrumentReader) -> None:
        """Test get_source_ticker with PIT query."""
        reader._client.fetchone = Mock(return_value={"source_ticker": "600000.SH"})

        result = reader.get_source_ticker(100000001, "tushare", asof="2024-01-01")

        assert result == "600000.SH"
        # Verify SQL includes PIT conditions
        call_args = reader._client.fetchone.call_args
        sql = call_args[0][0]
        assert "effective_from <= ?" in sql

    def test_find_securities(self, reader: InstrumentReader) -> None:
        """Test find_securities with filters."""
        rows = [
            {
                "instrument_id": 100000001,
                "symbol": "600000",
                "name": "浦发银行",
                "exchange": "SSE",
                "asset_class": "stock",
            },
        ]
        reader._client.fetchall = Mock(return_value=rows)

        result = reader.find_securities(exchange="SSE", asset_class="stock")

        assert len(result) == 1
        assert result["instrument_id"][0] == 100000001

    def test_list_instrument_ids(self, reader: InstrumentReader) -> None:
        """Test list_instrument_ids."""
        rows = [
            {"instrument_id": 100000001},
            {"instrument_id": 100000002},
        ]
        reader._client.fetchall = Mock(return_value=rows)

        result = reader.list_instrument_ids()

        assert len(result) == 2
        assert 100000001 in result
        assert 100000002 in result

    def test_get_symbol(self, reader: InstrumentReader) -> None:
        """Test get_symbol."""
        reader._client.fetchone = Mock(return_value={"symbol": "600000"})

        result = reader.get_symbol(100000001)

        assert result == "600000"

    def test_get_symbol_not_found(self, reader: InstrumentReader) -> None:
        """Test get_symbol returns None."""
        reader._client.fetchone = Mock(return_value=None)

        result = reader.get_symbol(999)

        assert result is None

    def test_get_instrument_id_symbol_map(self, reader: InstrumentReader) -> None:
        """Test get_instrument_id_symbol_map."""
        rows = [
            {"instrument_id": 100000001, "symbol": "600000"},
            {"instrument_id": 100000002, "symbol": "600004"},
        ]
        reader._client.fetchall = Mock(return_value=rows)

        result = reader.get_instrument_id_symbol_map([100000001, 100000002])

        assert len(result) == 2
        assert result[100000001] == "600000"
        assert result[100000002] == "600004"
