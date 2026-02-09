"""Integration tests for IndustryMappingReader and IndustryMappingWriter."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from ditto_datahub.stores.metadata.industry.industry_mapping_reader import (
    IndustryMappingReader,
)
from ditto_datahub.stores.metadata.industry.industry_mapping_writer import (
    IndustryMappingWriter,
)
from ditto_datahub.stores.metadata.industry.models import IndustryMapping


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
        CREATE TABLE IF NOT EXISTS industry_mapping (
            instrument_id INTEGER NOT NULL,
            industry_id TEXT NOT NULL,
            source TEXT DEFAULT 'sw',
            effective_from TEXT NOT NULL,
            effective_to TEXT,
            entry_reason TEXT,
            PRIMARY KEY (instrument_id, effective_from)
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
) -> IndustryMappingReader:
    """Create IndustryMappingReader with real dependencies."""
    return IndustryMappingReader(sqlite_client, cache_manager)


@pytest.fixture
def writer(
    sqlite_client: Any,
    cache_manager: Any,
) -> IndustryMappingWriter:
    """Create IndustryMappingWriter with real dependencies."""
    return IndustryMappingWriter(sqlite_client, cache_manager)


class TestIndustryMappingIntegration:
    """Integration tests for IndustryMapping Reader and Writer."""

    def test_write_then_read(
        self,
        writer: IndustryMappingWriter,
        reader: IndustryMappingReader,
    ) -> None:
        """Test writing then reading mapping."""
        mapping = IndustryMapping(
            instrument_id=1,
            industry_id="801010",
            effective_from="2024-01-01",
            entry_reason="首次入选",
        )

        # Write
        writer.update_mapping(mapping)

        # Read
        result = reader.get_stock_industry(1)

        assert result is not None
        assert result["instrument_id"] == 1
        assert result["industry_id"] == "801010"
        assert result["source"] == "sw"
        assert result["effective_from"] == "2024-01-01"

    def test_update_changes_industry(
        self,
        writer: IndustryMappingWriter,
        reader: IndustryMappingReader,
    ) -> None:
        """Test updating stock to different industry."""
        # Initial mapping
        mapping1 = IndustryMapping(
            instrument_id=1,
            industry_id="801010",
            effective_from="2024-01-01",
        )
        writer.update_mapping(mapping1)

        # Update to new industry
        mapping2 = IndustryMapping(
            instrument_id=1,
            industry_id="801020",
            effective_from="2024-06-01",
            entry_reason="行业调整",
        )
        writer.update_mapping(mapping2)

        # Current should be new industry
        result = reader.get_stock_industry(1)
        assert result["industry_id"] == "801020"

        # PIT query before change should show old industry
        result_mar = reader.get_stock_industry(1, asof="2024-03-01")
        assert result_mar["industry_id"] == "801010"

    def test_get_stocks_after_updates(
        self,
        writer: IndustryMappingWriter,
        reader: IndustryMappingReader,
    ) -> None:
        """Test get_stocks reflects industry changes."""
        # Add stocks to industry
        for stock_id in [1, 2, 3]:
            writer.update_mapping(
                IndustryMapping(
                    instrument_id=stock_id,
                    industry_id="801010",
                    effective_from="2024-01-01",
                ),
            )

        stocks = reader.get_stocks("801010")
        assert set(stocks) == {1, 2, 3}

        # Move stock 2 to different industry
        writer.update_mapping(
            IndustryMapping(
                instrument_id=2,
                industry_id="801020",
                effective_from="2024-06-01",
            ),
        )

        # Current should only have 1 and 3
        stocks_current = reader.get_stocks("801010")
        assert set(stocks_current) == {1, 3}

        # PIT query before move should have all 3
        stocks_mar = reader.get_stocks("801010", asof="2024-03-01")
        assert set(stocks_mar) == {1, 2, 3}

    def test_write_invalidates_cache(
        self,
        writer: IndustryMappingWriter,
        reader: IndustryMappingReader,
    ) -> None:
        """Test that writing invalidates cache."""
        # Write initial data
        writer.update_mapping(
            IndustryMapping(
                instrument_id=1,
                industry_id="801010",
                effective_from="2024-01-01",
            ),
        )

        # First read to populate cache
        result1 = reader.get_stock_industry(1)
        assert result1["industry_id"] == "801010"

        # Update mapping
        writer.update_mapping(
            IndustryMapping(
                instrument_id=1,
                industry_id="801020",
                effective_from="2024-06-01",
            ),
        )

        # Read again - should see new data
        result2 = reader.get_stock_industry(1)
        assert result2["industry_id"] == "801020"

    def test_pit_query_across_changes(
        self,
        writer: IndustryMappingWriter,
        reader: IndustryMappingReader,
    ) -> None:
        """Test PIT queries correctly track changes over time."""
        # Stock 1: 801010 -> 801020 -> 801030
        writer.update_mapping(
            IndustryMapping(
                instrument_id=1,
                industry_id="801010",
                effective_from="2024-01-01",
            ),
        )
        writer.update_mapping(
            IndustryMapping(
                instrument_id=1,
                industry_id="801020",
                effective_from="2024-04-01",
            ),
        )
        writer.update_mapping(
            IndustryMapping(
                instrument_id=1,
                industry_id="801030",
                effective_from="2024-07-01",
            ),
        )

        # Query different points in time
        result_feb = reader.get_stock_industry(1, asof="2024-02-01")
        assert result_feb["industry_id"] == "801010"

        result_may = reader.get_stock_industry(1, asof="2024-05-01")
        assert result_may["industry_id"] == "801020"

        result_aug = reader.get_stock_industry(1, asof="2024-08-01")
        assert result_aug["industry_id"] == "801030"

        result_current = reader.get_stock_industry(1)
        assert result_current["industry_id"] == "801030"

    def test_get_stocks_pit_boundary_conditions(
        self,
        writer: IndustryMappingWriter,
        reader: IndustryMappingReader,
    ) -> None:
        """Test PIT queries at effective_from boundaries."""
        # Stock joins industry on 2024-06-01
        writer.update_mapping(
            IndustryMapping(
                instrument_id=1,
                industry_id="801020",
                effective_from="2024-06-01",
            ),
        )

        # Query exactly on effective_from date
        result = reader.get_stock_industry(1, asof="2024-06-01")
        assert result is not None
        assert result["industry_id"] == "801020"

        # Query day before
        result_before = reader.get_stock_industry(1, asof="2024-05-31")
        assert result_before is None
