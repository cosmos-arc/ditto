"""Tests for UniverseReader."""

from __future__ import annotations

from unittest.mock import Mock

import pytest
from ditto_datahub.stores.metadata.universe.universe_reader import UniverseReader


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
def reader(mock_client: Mock, mock_cache: Mock) -> UniverseReader:
    """Create UniverseReader instance."""
    return UniverseReader(mock_client, mock_cache)


class TestUniverseReader:
    """Test suite for UniverseReader."""

    def test_get_universe_found(self, reader: UniverseReader) -> None:
        """Test get_universe returns universe data."""
        # Setup mock to return a universe
        mock_universe = {
            "universe_id": "test_universe",
            "name": "Test Universe",
            "description": "Test",
            "universe_type": "custom",
            "source_ref": None,
        }
        reader._client.fetchone = Mock(return_value=mock_universe)

        result = reader.get_universe("test_universe")

        assert result is not None
        assert result["universe_id"] == "test_universe"
        assert result["name"] == "Test Universe"

    def test_get_universe_not_found(self, reader: UniverseReader) -> None:
        """Test get_universe returns None for non-existent universe."""
        reader._client.fetchone = Mock(return_value=None)

        result = reader.get_universe("nonexistent")

        assert result is None

    def test_get_universe_cache_hit(self, reader: UniverseReader) -> None:
        """Test get_universe returns cached data."""
        cached_universe = {
            "universe_id": "test_universe",
            "name": "Cached Universe",
        }
        reader._cache.get = Mock(return_value=cached_universe)

        result = reader.get_universe("test_universe")

        assert result == cached_universe
        reader._cache.get.assert_called_once_with("universe:test_universe")
        # Should not query database
        reader._client.fetchone.assert_not_called()

    def test_get_universe_cache_miss(self, reader: UniverseReader) -> None:
        """Test get_universe queries database on cache miss."""
        reader._cache.get = Mock(return_value=None)

        mock_universe = {
            "universe_id": "test_universe",
            "name": "Test Universe",
            "description": "Test",
            "universe_type": "custom",
            "source_ref": None,
        }
        reader._client.fetchone = Mock(return_value=mock_universe)

        result = reader.get_universe("test_universe")

        assert result is not None
        # Should cache the result
        reader._cache.set.assert_called_once_with(
            "universe:test_universe", mock_universe
        )

    def test_list_universes_all(self, reader: UniverseReader) -> None:
        """Test list_universes returns all universes."""
        rows = [
            {"universe_id": "u1", "name": "Universe 1", "universe_type": "custom"},
            {"universe_id": "u2", "name": "Universe 2", "universe_type": "index"},
        ]
        reader._client.fetchall = Mock(return_value=rows)

        result = reader.list_universes()

        assert len(result) == 2
        assert "u1" in result["universe_id"].to_list()
        assert "u2" in result["universe_id"].to_list()

    def test_list_universes_empty(self, reader: UniverseReader) -> None:
        """Test list_universes returns empty DataFrame when no universes."""
        reader._client.fetchall = Mock(return_value=[])

        result = reader.list_universes()

        assert result.is_empty()

    def test_list_universes_with_filter(self, reader: UniverseReader) -> None:
        """Test list_universes with type filter."""
        rows = [
            {"universe_id": "u1", "name": "Universe 1", "universe_type": "custom"},
            {"universe_id": "u2", "name": "Universe 2", "universe_type": "custom"},
        ]
        reader._client.fetchall = Mock(return_value=rows)

        result = reader.list_universes(universe_type="custom")

        assert len(result) == 2
        # Verify SQL includes WHERE clause
        call_args = reader._client.fetchall.call_args
        sql = call_args[0][0]
        assert "WHERE universe_type = ?" in sql
        assert call_args[0][1] == ["custom"]

    def test_get_constituents_current(self, reader: UniverseReader) -> None:
        """Test get_constituents returns current constituents."""
        rows = [
            {
                "universe_id": "test_u",
                "instrument_id": 100000001,
                "effective_from": "2020-01-01",
                "effective_to": None,
                "weight": 1.0,
            },
            {
                "universe_id": "test_u",
                "instrument_id": 100000002,
                "effective_from": "2020-01-01",
                "effective_to": None,
                "weight": 1.0,
            },
        ]
        reader._client.fetchall = Mock(return_value=rows)

        result = reader.get_constituents("test_u")

        assert len(result) == 2
        assert 100000001 in result["instrument_id"].to_list()
        assert 100000002 in result["instrument_id"].to_list()

    def test_get_constituents_with_asof(self, reader: UniverseReader) -> None:
        """Test get_constituents with PIT query."""
        rows = [
            {
                "universe_id": "test_u",
                "instrument_id": 100000001,
                "effective_from": "2020-01-01",
                "effective_to": None,
                "weight": 1.0,
            },
        ]
        reader._client.fetchall = Mock(return_value=rows)

        result = reader.get_constituents("test_u", asof="2021-01-01")

        assert len(result) == 1
        # Verify SQL includes PIT conditions
        call_args = reader._client.fetchall.call_args
        sql = call_args[0][0]
        assert "effective_from <= ?" in sql
        assert "(effective_to IS NULL OR effective_to > ?)" in sql

    def test_get_constituents_empty(self, reader: UniverseReader) -> None:
        """Test get_constituents returns empty DataFrame when no constituents."""
        reader._client.fetchall = Mock(return_value=[])

        result = reader.get_constituents("test_u")

        assert result.is_empty()

    def test_get_constituent_instrument_ids(self, reader: UniverseReader) -> None:
        """Test get_constituent_instrument_ids returns list of IDs."""
        rows = [
            {
                "universe_id": "test_u",
                "instrument_id": 100000001,
                "effective_from": "2020-01-01",
                "effective_to": None,
                "weight": 1.0,
            },
            {
                "universe_id": "test_u",
                "instrument_id": 100000002,
                "effective_from": "2020-01-01",
                "effective_to": None,
                "weight": 1.0,
            },
        ]
        reader._client.fetchall = Mock(return_value=rows)

        result = reader.get_constituent_instrument_ids("test_u")

        assert len(result) == 2
        assert 100000001 in result
        assert 100000002 in result

    def test_get_constituent_instrument_ids_empty(self, reader: UniverseReader) -> None:
        """Test get_constituent_instrument_ids returns empty list."""
        reader._client.fetchall = Mock(return_value=[])

        result = reader.get_constituent_instrument_ids("test_u")

        assert result == []
