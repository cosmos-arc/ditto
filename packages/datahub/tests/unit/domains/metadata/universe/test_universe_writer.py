"""Tests for UniverseWriter."""

from __future__ import annotations

from unittest.mock import Mock

import pytest
from ditto_datahub.stores.metadata.universe.universe_writer import UniverseWriter


@pytest.fixture
def mock_client() -> Mock:
    """Create mock SQLite client."""
    client = Mock()
    client.execute = Mock()
    client.executemany = Mock()
    client.commit = Mock()
    return client


@pytest.fixture
def mock_cache() -> Mock:
    """Create mock cache manager."""
    cache = Mock()
    cache.invalidate_pattern = Mock(return_value=0)
    return cache


@pytest.fixture
def writer(mock_client: Mock, mock_cache: Mock) -> UniverseWriter:
    """Create UniverseWriter instance."""
    return UniverseWriter(mock_client, mock_cache)


class TestUniverseWriter:
    """Test suite for UniverseWriter."""

    def test_create_universe(self, writer: UniverseWriter) -> None:
        """Test create_universe executes correct SQL."""
        writer.create_universe(
            universe_id="test_universe",
            name="Test Universe",
            description="Test description",
            universe_type="custom",
            source_ref="test_ref",
        )

        # Verify execute was called
        assert writer._client.execute.called

        # Get the SQL and params from the call
        call_args = writer._client.execute.call_args
        sql = call_args[0][0]
        params = call_args[0][1]

        assert "INSERT INTO universe" in sql
        assert "universe_id, name, description, universe_type, source_ref" in sql
        assert params == [
            "test_universe",
            "Test Universe",
            "Test description",
            "custom",
            "test_ref",
        ]
        assert "VALUES (?, ?, ?, ?, ?)" in sql

    def test_create_universe_minimal(self, writer: UniverseWriter) -> None:
        """Test create_universe with minimal parameters."""
        writer.create_universe(
            universe_id="minimal_u",
            name="Minimal Universe",
        )

        # Verify commit was called
        writer._client.commit.assert_called_once()

        # Verify cache invalidation
        writer._cache.invalidate_pattern.assert_called_once_with("universe:*")

    def test_create_universe_without_optional_params(
        self, writer: UniverseWriter
    ) -> None:
        """Test create_universe with only required parameters."""
        writer.create_universe(
            universe_id="test_u",
            name="Test U",
        )

        # Get params from call
        call_args = writer._client.execute.call_args
        params = call_args[0][1]

        # description, universe_type, source_ref should be None/default
        assert len(params) == 5  # universe_id, name, description, type, ref

    def test_add_constituents(self, writer: UniverseWriter) -> None:
        """Test add_constituents executes batch insert."""
        records = [
            {
                "instrument_id": 100000001,
                "effective_from": "2020-01-01",
                "weight": 1.0,
            },
            {
                "instrument_id": 100000002,
                "effective_from": "2020-01-01",
                "weight": 0.5,
            },
        ]

        count = writer.add_constituents("test_u", records)

        assert count == 2
        assert writer._client.executemany.called

        # Get the SQL from the call
        call_args = writer._client.executemany.call_args
        sql = call_args[0][0]
        params_list = call_args[0][1]

        assert "INSERT INTO universe_constituent" in sql
        assert len(params_list) == 2

    def test_add_constituents_with_source_info(self, writer: UniverseWriter) -> None:
        """Test add_constituents with source information."""
        records = [
            {
                "instrument_id": 100000001,
                "effective_from": "2020-01-01",
                "weight": 1.0,
                "source": "tushare",
                "source_ticker": "600000.SH",
            },
        ]

        writer.add_constituents("test_u", records)

        # Get params from call
        call_args = writer._client.executemany.call_args
        params_list = call_args[0][1]
        params = params_list[0]

        # Verify all fields are included
        assert params[5] == "tushare"  # source
        assert params[6] == "600000.SH"  # source_ticker

    def test_add_constituents_invalidates_cache(self, writer: UniverseWriter) -> None:
        """Test add_constituents invalidates cache."""
        records = [
            {
                "instrument_id": 100000001,
                "effective_from": "2020-01-01",
                "weight": 1.0,
            },
        ]

        writer.add_constituents("test_u", records)

        # Verify cache invalidation
        writer._cache.invalidate_pattern.assert_called_once_with(
            "universe:constituents:*"
        )

    def test_remove_constituent(self, writer: UniverseWriter) -> None:
        """Test remove_constituent sets effective_to."""
        writer.remove_constituent("test_u", 100000001, "2021-06-30")

        # Verify execute was called
        assert writer._client.execute.called

        # Get the SQL and params from the call
        call_args = writer._client.execute.call_args
        sql = call_args[0][0]
        params = call_args[0][1]

        assert "UPDATE universe_constituent" in sql
        assert "SET effective_to = ?" in sql
        assert "WHERE universe_id = ?" in sql
        assert "AND instrument_id = ?" in sql
        assert "AND effective_to IS NULL" in sql
        assert params == ["2021-06-30", "test_u", 100000001]

    def test_remove_constituent_invalidates_cache(self, writer: UniverseWriter) -> None:
        """Test remove_constituent invalidates cache."""
        writer.remove_constituent("test_u", 100000001, "2021-06-30")

        # Verify cache invalidation
        writer._cache.invalidate_pattern.assert_called_once_with(
            "universe:constituents:*"
        )

    def test_add_constituents_empty_list(self, writer: UniverseWriter) -> None:
        """Test add_constituents with empty list."""
        count = writer.add_constituents("test_u", [])

        assert count == 0
        # executemany should not be called for empty list
        writer._client.executemany.assert_not_called()
