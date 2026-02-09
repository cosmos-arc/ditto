"""Integration tests for UniverseReader and UniverseWriter."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from ditto_datahub.stores.metadata.universe.universe_reader import UniverseReader
from ditto_datahub.stores.metadata.universe.universe_writer import UniverseWriter
from ditto_foundation import SQLitePool


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    """Create temporary database path."""
    return tmp_path / "test.db"


@pytest.fixture
def pool(db_path: Path) -> SQLitePool:
    """Create real SQLite pool with test schema."""

    pool = SQLitePool(":memory:")

    # Create tables
    conn = pool.get_connection()
    conn.execute("""
        CREATE TABLE universe (
            universe_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT,
            universe_type TEXT NOT NULL DEFAULT 'custom',
            source_ref TEXT
        )
    """)

    conn.execute("""
        CREATE TABLE universe_constituent (
            universe_id TEXT NOT NULL,
            instrument_id INTEGER NOT NULL,
            effective_from TEXT NOT NULL,
            effective_to TEXT,
            weight REAL NOT NULL DEFAULT 1.0,
            source TEXT,
            source_ticker TEXT,
            PRIMARY KEY (universe_id, instrument_id, effective_from),
            FOREIGN KEY (instrument_id) REFERENCES instrument(instrument_id)
        )
    """)

    conn.execute("""
        CREATE TABLE instrument (
            instrument_id INTEGER PRIMARY KEY,
            symbol TEXT NOT NULL,
            name TEXT,
            exchange TEXT,
            asset_class TEXT,
            list_date TEXT
        )
    """)

    conn.commit()
    return pool


@pytest.fixture
def mock_client(pool: SQLitePool) -> Any:
    """Create mock SQLite client with real pool."""
    from unittest.mock import Mock

    client = Mock()
    client.execute = Mock(
        side_effect=lambda sql, params: pool.get_connection().execute(
            sql,
            params or [],
        ),
    )
    client.fetchone = Mock(
        side_effect=lambda sql, params: _fetchone_impl(
            pool,
            sql,
            params,
        ),
    )
    client.fetchall = Mock(
        side_effect=lambda sql, params: _fetchall_impl(
            pool,
            sql,
            params,
        ),
    )
    client.executemany = Mock(
        side_effect=lambda sql, params_list: _executemany_impl(
            pool,
            sql,
            params_list,
        ),
    )
    client.commit = Mock(side_effect=lambda: pool.get_connection().commit())
    return client


@pytest.fixture
def mock_cache() -> Any:
    """Create mock cache manager."""
    from unittest.mock import Mock

    cache = Mock()
    cache.get = Mock(return_value=None)
    cache.set = Mock()
    cache.invalidate = Mock()
    cache.invalidate_pattern = Mock(return_value=0)
    return cache


@pytest.fixture
def reader(mock_client: Any, mock_cache: Any) -> UniverseReader:
    """Create UniverseReader instance."""
    return UniverseReader(mock_client, mock_cache)


@pytest.fixture
def writer(mock_client: Any, mock_cache: Any) -> UniverseWriter:
    """Create UniverseWriter instance."""
    return UniverseWriter(mock_client, mock_cache)


def _fetchone_impl(
    pool: SQLitePool,
    sql: str,
    params: Any,
) -> dict[str, Any] | None:
    """Implementation for mock fetchone."""
    cursor = pool.get_connection().execute(sql, params or [])
    row = cursor.fetchone()
    if row:
        columns = [desc[0] for desc in cursor.description]
        return dict(zip(columns, row, strict=True))
    return None


def _fetchall_impl(
    pool: SQLitePool,
    sql: str,
    params: Any,
) -> list[dict[str, Any]]:
    """Implementation for mock fetchall."""
    cursor = pool.get_connection().execute(sql, params or [])
    rows = cursor.fetchall()
    if not rows:
        return []
    columns = [desc[0] for desc in cursor.description]
    return [dict(zip(columns, row, strict=True)) for row in rows]


def _executemany_impl(
    pool: SQLitePool,
    sql: str,
    params_list: Any,
) -> None:
    """Implementation for mock executemany."""
    conn = pool.get_connection()
    for params in params_list:
        conn.execute(sql, params)


class TestUniverseIntegration:
    """Integration tests for UniverseReader and UniverseWriter."""

    def test_write_then_read(
        self, writer: UniverseWriter, reader: UniverseReader
    ) -> None:
        """Test creating universe and reading it back."""
        # Create universe
        writer.create_universe(
            universe_id="test_u",
            name="Test Universe",
            description="Test universe",
            universe_type="custom",
        )

        # Read it back
        result = reader.get_universe("test_u")

        assert result is not None
        assert result["universe_id"] == "test_u"
        assert result["name"] == "Test Universe"
        assert result["description"] == "Test universe"

    def test_write_invalidates_cache(
        self, writer: UniverseWriter, reader: UniverseReader, mock_cache: Any
    ) -> None:
        """Test that writing invalidates cache."""
        # Create universe
        writer.create_universe("test_u", "Test Universe")

        # Verify cache invalidation was called
        mock_cache.invalidate_pattern.assert_called_with("universe:*")

    def test_add_constituents_then_read(
        self, writer: UniverseWriter, reader: UniverseReader, pool: SQLitePool
    ) -> None:
        """Test adding constituents and reading them back."""
        # Create instrument first (FK constraint)
        pool.get_connection().execute(
            """INSERT INTO instrument
            (instrument_id, symbol, name, exchange, asset_class, list_date)
            VALUES (?, ?, ?, ?, ?, ?)""",
            [100000001, "TEST001", "Test", "SSE", "stock", "2020-01-01"],
        )
        pool.get_connection().commit()

        # Create universe
        writer.create_universe("test_u", "Test Universe")

        # Add constituents
        records = [
            {
                "instrument_id": 100000001,
                "effective_from": "2020-01-01",
                "weight": 1.0,
            },
        ]
        writer.add_constituents("test_u", records)

        # Read constituents back
        constituents = reader.get_constituents("test_u")

        assert len(constituents) == 1
        assert constituents["instrument_id"][0] == 100000001

    def test_pit_query_across_changes(
        self, writer: UniverseWriter, reader: UniverseReader, pool: SQLitePool
    ) -> None:
        """Test PIT query across constituent changes."""
        # Create instruments
        pool.get_connection().execute(
            """INSERT INTO instrument
            (instrument_id, symbol, name, exchange, asset_class, list_date)
            VALUES (?, ?, ?, ?, ?, ?)""",
            [100000001, "TEST001", "Test", "SSE", "stock", "2020-01-01"],
        )
        pool.get_connection().execute(
            """INSERT INTO instrument
            (instrument_id, symbol, name, exchange, asset_class, list_date)
            VALUES (?, ?, ?, ?, ?, ?)""",
            [100000002, "TEST002", "Test", "SSE", "stock", "2020-01-01"],
        )
        pool.get_connection().commit()

        # Create universe
        writer.create_universe("test_u", "Test Universe")

        # Add first constituent
        records = [
            {
                "instrument_id": 100000001,
                "effective_from": "2020-01-01",
                "weight": 1.0,
            },
        ]
        writer.add_constituents("test_u", records)

        # Remove first and add second
        writer.remove_constituent("test_u", 100000001, "2021-06-30")

        records = [
            {
                "instrument_id": 100000002,
                "effective_from": "2021-07-01",
                "weight": 1.0,
            },
        ]
        writer.add_constituents("test_u", records)

        # Query before change
        sids_2020 = reader.get_constituent_instrument_ids("test_u", asof="2021-01-01")
        assert 100000001 in sids_2020
        assert 100000002 not in sids_2020

        # Query after change
        sids_2021 = reader.get_constituent_instrument_ids("test_u", asof="2021-07-15")
        assert 100000001 not in sids_2021
        assert 100000002 in sids_2021

    def test_list_universes_after_creation(
        self, writer: UniverseWriter, reader: UniverseReader
    ) -> None:
        """Test listing universes after creating multiple."""
        # Create multiple universes
        writer.create_universe("u1", "Universe 1", universe_type="custom")
        writer.create_universe("u2", "Universe 2", universe_type="index")
        writer.create_universe("u3", "Universe 3", universe_type="custom")

        # List all
        all_universes = reader.list_universes()
        assert len(all_universes) == 3

        # Filter by type
        custom_universes = reader.list_universes(universe_type="custom")
        assert len(custom_universes) == 2
