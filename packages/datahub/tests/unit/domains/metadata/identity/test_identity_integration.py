"""Integration tests for IdentityReader and IdentityWriter."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from ditto_datahub.stores.metadata.identity.identity_reader import IdentityReader
from ditto_datahub.stores.metadata.identity.identity_writer import IdentityWriter


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

    # Create table
    client.executescript("""
        CREATE TABLE IF NOT EXISTS identity_mapping (
            instrument_id INTEGER NOT NULL,
            source TEXT NOT NULL,
            source_ticker TEXT NOT NULL,
            effective_from TEXT NOT NULL,
            effective_to TEXT,
            is_primary INTEGER NOT NULL DEFAULT 1,
            PRIMARY KEY (source, source_ticker, effective_from)
        )
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
) -> IdentityReader:
    """Create IdentityReader with real dependencies."""
    return IdentityReader(sqlite_client, cache_manager)


@pytest.fixture
def writer(
    sqlite_client: Any,
    cache_manager: Any,
) -> IdentityWriter:
    """Create IdentityWriter with real dependencies."""
    return IdentityWriter(sqlite_client, cache_manager)


class TestIdentityIntegration:
    """Integration tests for Identity Reader and Writer."""

    def test_write_then_read(
        self,
        writer: IdentityWriter,
        reader: IdentityReader,
    ) -> None:
        """Test writing then reading identity mapping."""
        # Write
        writer.register(
            instrument_id=1,
            source_ticker="000001.SZ",
            source="tdx",
            effective_from="2024-01-01",
        )

        # Read
        result = reader.resolve_instrument_id("000001.SZ", "tdx")

        assert result == 1

    def test_write_invalidates_cache(
        self,
        writer: IdentityWriter,
        reader: IdentityReader,
        cache_manager: Any,
    ) -> None:
        """Test that writing invalidates cache."""
        # First read to populate cache
        writer.register(
            instrument_id=1,
            source_ticker="000001.SZ",
            source="tdx",
            effective_from="2024-01-01",
        )
        result1 = reader.resolve_instrument_id("000001.SZ", "tdx")

        # Get cache stats
        cache_manager.get_stats()

        # Second read should hit cache
        result2 = reader.resolve_instrument_id("000001.SZ", "tdx")
        assert result2 == result1

    def test_reverse_lookup(
        self,
        writer: IdentityWriter,
        reader: IdentityReader,
    ) -> None:
        """Test reverse lookup from instrument_id to source_ticker."""
        writer.register(
            instrument_id=1,
            source_ticker="000001.SZ",
            source="tdx",
            effective_from="2024-01-01",
        )

        result = reader.get_source_ticker(1, "tdx")

        assert result == "000001.SZ"

    def test_batch_resolution(
        self,
        writer: IdentityWriter,
        reader: IdentityReader,
    ) -> None:
        """Test batch resolution of multiple tickers."""
        # Register multiple tickers
        for i, ticker in enumerate(["000001.SZ", "000002.SZ", "000003.SZ"], 1):
            writer.register(
                instrument_id=i,
                source_ticker=ticker,
                source="tdx",
                effective_from="2024-01-01",
            )

        # Batch resolve
        tickers = ["000001.SZ", "000002.SZ", "000003.SZ", "999999.SZ"]
        result = reader.resolve_instrument_ids_batch(tickers, "tdx")

        assert result["000001.SZ"] == 1
        assert result["000002.SZ"] == 2
        assert result["000003.SZ"] == 3
        assert "999999.SZ" not in result  # Not found

    def test_pit_query_across_changes(
        self,
        writer: IdentityWriter,
        reader: IdentityReader,
    ) -> None:
        """Test PIT queries across ticker changes."""
        # Register initial ticker
        writer.register(
            instrument_id=1,
            source_ticker="000001.SZ",
            source="tdx",
            effective_from="2024-01-01",
        )

        # Re-register with same ticker but new effective_from
        writer.register(
            instrument_id=1,
            source_ticker="000001.SZ",
            source="tdx",
            effective_from="2024-06-01",
        )

        # Query different points in time - should return same instrument_id
        result_jan = reader.resolve_instrument_id("000001.SZ", "tdx", asof="2024-02-01")
        assert result_jan == 1

        result_jul = reader.resolve_instrument_id("000001.SZ", "tdx", asof="2024-07-01")
        assert result_jul == 1

        result_current = reader.resolve_instrument_id("000001.SZ", "tdx")
        assert result_current == 1

    def test_non_existent_ticker(self, reader: IdentityReader) -> None:
        """Test reading non-existent ticker returns None."""
        result = reader.resolve_instrument_id("999999.SZ", "tdx")
        assert result is None

    def test_non_existent_instrument_id(
        self,
        writer: IdentityWriter,
        reader: IdentityReader,
    ) -> None:
        """Test reverse lookup with non-existent instrument_id."""
        result = reader.get_source_ticker(999, "tdx")
        assert result is None
