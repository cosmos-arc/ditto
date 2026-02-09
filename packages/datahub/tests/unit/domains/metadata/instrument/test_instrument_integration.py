"""Integration tests for InstrumentReader and InstrumentWriter."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from ditto_datahub.stores.metadata.instrument.instrument_reader import (
    InstrumentReader,
)
from ditto_datahub.stores.metadata.instrument.instrument_writer import (
    InstrumentWriter,
)
from ditto_datahub.stores.metadata.instrument.models import InstrumentRegistration


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    """Create temporary database path."""
    return tmp_path / "test.db"


@pytest.fixture
def sqlite_client(db_path: Path) -> Any:
    """Create real SQLite client with initialized schema."""
    from ditto_datahub.stores.sqlite_client import SQLiteClient
    from ditto_foundation import SQLitePool

    pool = SQLitePool(str(db_path))
    client = SQLiteClient(pool)

    # Create tables
    client.executescript("""
        CREATE TABLE IF NOT EXISTS instrument (
            instrument_id INTEGER PRIMARY KEY,
            symbol TEXT NOT NULL,
            name TEXT,
            exchange TEXT,
            board TEXT,
            asset_class TEXT,
            list_date TEXT,
            is_active INTEGER DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS instrument_mapping (
            instrument_id INTEGER NOT NULL,
            source TEXT NOT NULL,
            source_ticker TEXT NOT NULL,
            effective_from TEXT NOT NULL,
            effective_to TEXT,
            is_primary INTEGER DEFAULT 1,
            PRIMARY KEY (source, source_ticker, effective_from)
        );
    """)

    return client


@pytest.fixture
def cache_manager() -> Any:
    """Create real cache manager."""
    from ditto_foundation.cache import DataCache

    return DataCache(enable_metrics=False)


@pytest.fixture
def reader(
    sqlite_client: Any,
    cache_manager: Any,
) -> InstrumentReader:
    """Create InstrumentReader with real dependencies."""
    return InstrumentReader(sqlite_client, cache_manager)


@pytest.fixture
def writer(
    sqlite_client: Any,
    cache_manager: Any,
) -> InstrumentWriter:
    """Create InstrumentWriter with real dependencies."""
    return InstrumentWriter(sqlite_client, cache_manager)


@pytest.fixture
def sample_registration() -> InstrumentRegistration:
    """Create sample instrument registration."""
    return InstrumentRegistration(
        symbol="600000",
        name="浦发银行",
        source_ticker="600000.SH",
        source="tushare",
        exchange="SSE",
        board="主板",
        asset_class="stock",
        list_date="1999-11-10",
    )


class TestInstrumentIntegration:
    """Integration tests for Instrument Reader and Writer."""

    def test_write_then_read(
        self,
        writer: InstrumentWriter,
        reader: InstrumentReader,
        sample_registration: InstrumentRegistration,
    ) -> None:
        """Test writing then reading instrument."""
        # Write
        _ = writer.register(100000001, sample_registration)

        # Read by source_ticker
        result = reader.resolve_instrument_id("600000.SH", "tushare")

        assert result == 100000001

    def test_reverse_lookup(
        self,
        writer: InstrumentWriter,
        reader: InstrumentReader,
        sample_registration: InstrumentRegistration,
    ) -> None:
        """Test reverse lookup from instrument_id to source_ticker."""
        writer.register(100000001, sample_registration)

        result = reader.get_source_ticker(100000001, "tushare")

        assert result == "600000.SH"

    def test_get_symbol(
        self,
        writer: InstrumentWriter,
        reader: InstrumentReader,
        sample_registration: InstrumentRegistration,
    ) -> None:
        """Test getting symbol by instrument_id."""
        writer.register(100000001, sample_registration)

        result = reader.get_symbol(100000001)

        assert result == "600000"

    def test_instrument_id_symbol_map(
        self,
        writer: InstrumentWriter,
        reader: InstrumentReader,
        sample_registration: InstrumentRegistration,
    ) -> None:
        """Test getting batch instrument_id to symbol mapping."""
        # Register multiple instruments
        reg1 = sample_registration
        reg2 = InstrumentRegistration(
            symbol="000001",
            name="平安银行",
            source_ticker="000001.SZ",
            source="tushare",
            exchange="SZSE",
            asset_class="stock",
            list_date="1991-04-03",
        )

        writer.register(100000001, reg1)
        writer.register(100000002, reg2)

        # Get mapping
        result = reader.get_instrument_id_symbol_map([100000001, 100000002])

        assert result[100000001] == "600000"
        assert result[100000002] == "000001"

    def test_find_securities(
        self,
        writer: InstrumentWriter,
        reader: InstrumentReader,
        sample_registration: InstrumentRegistration,
    ) -> None:
        """Test finding securities with filters."""
        writer.register(100000001, sample_registration)

        # Find by exchange
        result = reader.find_securities(exchange="SSE")

        assert len(result) == 1
        assert result["symbol"][0] == "600000"
        assert result["exchange"][0] == "SSE"

    def test_list_instrument_ids(
        self,
        writer: InstrumentWriter,
        reader: InstrumentReader,
        sample_registration: InstrumentRegistration,
    ) -> None:
        """Test listing all instrument_ids with filters."""
        writer.register(100000001, sample_registration)

        # List all active stocks on SSE
        result = reader.list_instrument_ids(
            asset_class="stock",
            exchange="SSE",
            is_active=True,
        )

        assert 100000001 in result

    def test_batch_resolution(
        self,
        writer: InstrumentWriter,
        reader: InstrumentReader,
    ) -> None:
        """Test batch resolution of multiple tickers."""
        # Register multiple tickers
        registrations = [
            InstrumentRegistration(
                symbol="600000",
                name="浦发银行",
                source_ticker="600000.SH",
                source="tushare",
                exchange="SSE",
                asset_class="stock",
                list_date="1999-11-10",
            ),
            InstrumentRegistration(
                symbol="000001",
                name="平安银行",
                source_ticker="000001.SZ",
                source="tushare",
                exchange="SZSE",
                asset_class="stock",
                list_date="1991-04-03",
            ),
        ]

        for i, reg in enumerate(registrations, 100000001):
            writer.register(i, reg)

        # Batch resolve
        tickers = ["600000.SH", "000001.SZ", "999999.SH"]
        result = reader.resolve_instrument_ids_batch(tickers, "tushare")

        assert result["600000.SH"] == 100000001
        assert result["000001.SZ"] == 100000002
        assert "999999.SH" not in result  # Not found

    def test_cache_invalidation_after_write(
        self,
        writer: InstrumentWriter,
        reader: InstrumentReader,
        cache_manager: Any,
        sample_registration: InstrumentRegistration,
    ) -> None:
        """Test that cache is invalidated after writing."""
        # First write
        writer.register(100000001, sample_registration)

        # First read to populate cache
        result1 = reader.resolve_instrument_id("600000.SH", "tushare")

        # Write a different ticker (should invalidate pattern cache)
        reg2 = InstrumentRegistration(
            symbol="600001",
            name="白云机场",
            source_ticker="600001.SH",
            source="tushare",
            exchange="SSE",
            asset_class="stock",
            list_date="2003-04-28",
        )
        writer.register(100000002, reg2)

        # Read the new ticker
        result2 = reader.resolve_instrument_id("600001.SH", "tushare")

        assert result1 == 100000001
        assert result2 == 100000002

    def test_non_existent_instrument(self, reader: InstrumentReader) -> None:
        """Test reading non-existent instrument returns None."""
        result = reader.resolve_instrument_id("999999.SH", "tushare")
        assert result is None

    def test_non_existent_instrument_id(self, reader: InstrumentReader) -> None:
        """Test getting symbol for non-existent instrument_id."""
        result = reader.get_symbol(999999999)
        assert result is None

    def test_find_securities_empty_result(self, reader: InstrumentReader) -> None:
        """Test find_securities returns empty DataFrame when no match."""
        result = reader.find_securities(exchange="NONEXISTENT")
        assert result.is_empty()
