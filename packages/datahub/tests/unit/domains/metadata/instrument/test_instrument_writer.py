"""Tests for InstrumentWriter."""

from __future__ import annotations

from unittest.mock import Mock

import pytest
from ditto_datahub.stores.metadata.instrument.instrument_writer import InstrumentWriter
from ditto_datahub.stores.metadata.instrument.models import InstrumentRegistration


@pytest.fixture
def mock_client() -> Mock:
    """Create mock SQLite client."""
    client = Mock()
    client.execute = Mock()
    client.commit = Mock()
    client.rollback = Mock()
    return client


@pytest.fixture
def mock_cache() -> Mock:
    """Create mock cache manager."""
    cache = Mock()
    cache.invalidate = Mock()
    cache.invalidate_pattern = Mock(return_value=0)
    return cache


@pytest.fixture
def writer(mock_client: Mock, mock_cache: Mock) -> InstrumentWriter:
    """Create InstrumentWriter instance."""
    return InstrumentWriter(mock_client, mock_cache)


class TestInstrumentWriter:
    """Test suite for InstrumentWriter."""

    def test_register(self, writer: InstrumentWriter) -> None:
        """Test register executes correct SQL."""
        registration = InstrumentRegistration(
            symbol="600000",
            name="浦发银行",
            source_ticker="600000.SH",
            source="tushare",
            exchange="SSE",
            board="主板",
            asset_class="stock",
            list_date="1999-11-10",
        )

        result = writer.register(100000001, registration)

        # Verify execute was called twice (instrument + mapping)
        assert writer._client.execute.call_count == 2

        # Verify commit was called
        writer._client.commit.assert_called_once()

        assert result == 100000001

    def test_register_invalidates_cache(
        self, writer: InstrumentWriter, mock_cache: Mock
    ) -> None:
        """Test register invalidates cache."""
        registration = InstrumentRegistration(
            symbol="600000",
            name="浦发银行",
            source_ticker="600000.SH",
            source="tushare",
            exchange="SSE",
            board="主板",
            asset_class="stock",
            list_date="1999-11-10",
        )

        writer.register(100000001, registration)

        # Verify cache invalidation was called
        mock_cache.invalidate.assert_called_once()
        mock_cache.invalidate_pattern.assert_called_once_with(
            "instrument_id_symbol_map:*"
        )

    def test_register_rollback_on_error(self, writer: InstrumentWriter) -> None:
        """Test register rolls back on exception."""
        registration = InstrumentRegistration(
            symbol="600000",
            name="浦发银行",
            source_ticker="600000.SH",
            source="tushare",
            exchange="SSE",
            board="主板",
            asset_class="stock",
            list_date="1999-11-10",
        )

        # Mock execute to raise exception
        writer._client.execute = Mock(side_effect=RuntimeError("DB error"))

        with pytest.raises(RuntimeError):
            writer.register(100000001, registration)

        # Verify rollback was called
        writer._client.rollback.assert_called_once()
