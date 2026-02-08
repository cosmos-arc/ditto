"""Tests for UniverseStore."""

import pytest
from ditto_datahub.domains.metadata.universe import UniverseStore
from ditto_datahub.stores.sqlite_client import SQLiteClient


@pytest.mark.integration
class TestUniverseStore:
    """
    Tests for UniverseStore.

    PIT (Pipeline Integration Tests) - tests complete data ingestion flow.
    These tests require more resources and time than unit tests.
    """

    @pytest.fixture(autouse=True)
    def setup(self, sqlite_client: SQLiteClient) -> None:
        """使用 fixture 自动注入已初始化的数据库客户端."""
        self.client = sqlite_client
        self.store = UniverseStore(self.client)

    def _create_securities(self, instrument_ids: list[int]) -> None:
        """Helper to create instrument records for testing."""
        for instrument_id in instrument_ids:
            self.client.execute(
                """INSERT INTO instrument
                (instrument_id, symbol, name, exchange, asset_class, list_date)
                VALUES (?, ?, ?, ?, ?, ?)""",
                [
                    instrument_id,
                    f"TEST{instrument_id}",
                    "Test",
                    "SSE",
                    "stock",
                    "2020-01-01",
                ],
            )
        self.client.commit()

    def test_universe_store_init(self) -> None:
        """Test UniverseStore initialization."""
        assert self.store._client is not None

    def test_create_universe(self) -> None:
        """Test creating a universe."""
        # Create a universe
        self.store.create_universe(
            universe_id="test_universe",
            name="Test Universe",
            description="Test universe for unit testing",
            universe_type="custom",
        )

        # Verify universe was created
        result = self.store.get_universe("test_universe")
        assert result is not None
        assert result["universe_id"] == "test_universe"
        assert result["name"] == "Test Universe"
        assert result["description"] == "Test universe for unit testing"
        assert result["universe_type"] == "custom"

    def test_create_universe_with_source_ref(self) -> None:
        """Test creating a universe with source reference."""
        self.store.create_universe(
            universe_id="index_300",
            name="CSI 300 Index",
            universe_type="index",
            source_ref="000300.SH",
        )

        result = self.store.get_universe("index_300")
        assert result is not None
        assert result["source_ref"] == "000300.SH"
        assert result["universe_type"] == "index"

    def test_get_universe_not_found(self) -> None:
        """Test getting non-existent universe returns None."""
        result = self.store.get_universe("nonexistent")
        assert result is None

    def test_list_universes(self) -> None:
        """Test listing all universes."""
        # Create multiple universes
        self.store.create_universe("universe1", "Universe 1", universe_type="custom")
        self.store.create_universe("universe2", "Universe 2", universe_type="index")
        self.store.create_universe("universe3", "Universe 3", universe_type="custom")

        # List all
        all_universes = self.store.list_universes()
        assert len(all_universes) == 3
        assert "universe1" in all_universes["universe_id"].to_list()
        assert "universe2" in all_universes["universe_id"].to_list()
        assert "universe3" in all_universes["universe_id"].to_list()

    def test_list_universes_with_filter(self) -> None:
        """Test listing universes with type filter."""
        # Create multiple universes
        self.store.create_universe("custom1", "Custom 1", universe_type="custom")
        self.store.create_universe("index1", "Index 1", universe_type="index")
        self.store.create_universe("custom2", "Custom 2", universe_type="custom")

        # Filter by type
        custom_universes = self.store.list_universes(universe_type="custom")
        assert len(custom_universes) == 2
        assert all(custom_universes["universe_type"] == "custom")

        index_universes = self.store.list_universes(universe_type="index")
        assert len(index_universes) == 1
        assert index_universes["universe_id"][0] == "index1"

    def test_add_constituents(self) -> None:
        """Test adding constituents to a universe."""
        # Create universe
        self.store.create_universe("test_u", "Test", universe_type="custom")

        # Create instrument records first (foreign key constraint)
        self._create_securities([100000001, 100000002, 100000003])

        # Add constituents
        records = [
            {"instrument_id": 100000001, "effective_from": "2020-01-01", "weight": 1.0},
            {"instrument_id": 100000002, "effective_from": "2020-01-01", "weight": 1.0},
            {"instrument_id": 100000003, "effective_from": "2020-01-01", "weight": 0.5},
        ]
        count = self.store.add_constituents("test_u", records)
        assert count == 3

    def test_get_constituents_current(self) -> None:
        """Test getting current constituents (asof=None)."""
        # Create universe and add constituents
        self.store.create_universe("test_u", "Test", universe_type="custom")

        self._create_securities([100000001, 100000002])

        records = [
            {"instrument_id": 100000001, "effective_from": "2020-01-01", "weight": 1.0},
            {"instrument_id": 100000002, "effective_from": "2020-01-01", "weight": 1.0},
        ]
        self.store.add_constituents("test_u", records)

        # Get current constituents
        constituents = self.store.get_constituents("test_u")
        assert len(constituents) == 2
        assert 100000001 in constituents["instrument_id"].to_list()
        assert 100000002 in constituents["instrument_id"].to_list()
        assert all(constituents["effective_to"].is_null())

    def test_get_constituents_with_asof(self) -> None:
        """Test PIT query with asof parameter."""
        # Create universe
        self.store.create_universe("test_u", "Test", universe_type="custom")

        self._create_securities([100000001, 100000002, 100000003])

        # Add constituents with different effective dates
        records = [
            {
                "instrument_id": 100000001,
                "effective_from": "2020-01-01",
                "effective_to": "2021-06-30",
                "weight": 1.0,
            },
            {
                "instrument_id": 100000002,
                "effective_from": "2020-01-01",
                "effective_to": None,
                "weight": 1.0,
            },
            {
                "instrument_id": 100000003,
                "effective_from": "2021-07-01",
                "effective_to": None,
                "weight": 1.0,
            },
        ]
        self.store.add_constituents("test_u", records)

        # Query as of 2021-01-01 (before first change)
        constituents_2021 = self.store.get_constituents("test_u", asof="2021-01-01")
        assert len(constituents_2021) == 2
        assert 100000001 in constituents_2021["instrument_id"].to_list()
        assert 100000002 in constituents_2021["instrument_id"].to_list()
        assert 100000003 not in constituents_2021["instrument_id"].to_list()

        # Query as of 2021-07-15 (after change)
        constituents_2021_07 = self.store.get_constituents("test_u", asof="2021-07-15")
        assert len(constituents_2021_07) == 2
        assert (
            100000001 not in constituents_2021_07["instrument_id"].to_list()
        )  # expired
        assert 100000002 in constituents_2021_07["instrument_id"].to_list()
        assert 100000003 in constituents_2021_07["instrument_id"].to_list()

    def test_get_constituents_sids(self) -> None:
        """Test getting constituent instrument_ids as list."""
        # Create universe and add constituents
        self.store.create_universe("test_u", "Test", universe_type="custom")

        self._create_securities([100000001, 100000002])

        records = [
            {"instrument_id": 100000001, "effective_from": "2020-01-01", "weight": 1.0},
            {"instrument_id": 100000002, "effective_from": "2020-01-01", "weight": 1.0},
        ]
        self.store.add_constituents("test_u", records)

        # Get instrument_ids
        instrument_ids = self.store.get_constituent_instrument_ids("test_u")
        assert len(instrument_ids) == 2
        assert 100000001 in instrument_ids
        assert 100000002 in instrument_ids

    def test_get_constituents_sids_with_asof(self) -> None:
        """Test getting constituent instrument_ids with PIT query."""
        # Create universe
        self.store.create_universe("test_u", "Test", universe_type="custom")

        self._create_securities([100000001, 100000002])

        # Add constituents with different dates
        records = [
            {
                "instrument_id": 100000001,
                "effective_from": "2020-01-01",
                "effective_to": "2021-06-30",
                "weight": 1.0,
            },
            {
                "instrument_id": 100000002,
                "effective_from": "2020-01-01",
                "weight": 1.0,
            },
        ]
        self.store.add_constituents("test_u", records)

        # Get instrument_ids as of 2020-06-01
        sids_2020 = self.store.get_constituent_instrument_ids(
            "test_u", asof="2020-06-01"
        )
        assert len(sids_2020) == 2

        # Get instrument_ids as of 2021-07-01
        sids_2021 = self.store.get_constituent_instrument_ids(
            "test_u", asof="2021-07-01"
        )
        assert len(sids_2021) == 1
        assert 100000002 in sids_2021

    def test_remove_constituent(self) -> None:
        """Test removing a constituent by setting effective_to."""
        # Create universe and add constituents
        self.store.create_universe("test_u", "Test", universe_type="custom")

        self._create_securities([100000001, 100000002])

        records = [
            {"instrument_id": 100000001, "effective_from": "2020-01-01", "weight": 1.0},
            {"instrument_id": 100000002, "effective_from": "2020-01-01", "weight": 1.0},
        ]
        self.store.add_constituents("test_u", records)

        # Remove one constituent
        self.store.remove_constituent("test_u", 100000001, "2021-06-30")

        # Verify it's no longer in current constituents
        current_sids = self.store.get_constituent_instrument_ids("test_u")
        assert 100000001 not in current_sids
        assert 100000002 in current_sids

        # But it should be in historical query before removal date
        historical_sids = self.store.get_constituent_instrument_ids(
            "test_u", asof="2021-01-01"
        )
        assert 100000001 in historical_sids

    def test_add_constituents_with_source_info(self) -> None:
        """Test adding constituents with source information."""
        # Create universe
        self.store.create_universe("test_u", "Test", universe_type="custom")

        self._create_securities([100000001])

        # Add constituents with source info
        records = [
            {
                "instrument_id": 100000001,
                "effective_from": "2020-01-01",
                "weight": 1.0,
                "source": "tushare",
                "source_ticker": "600000.SH",
            },
        ]
        self.store.add_constituents("test_u", records)

        # Verify source info is saved
        constituents = self.store.get_constituents("test_u")
        assert len(constituents) == 1
        assert constituents["source"][0] == "tushare"
        assert constituents["source_ticker"][0] == "600000.SH"

    def teardown_method(self) -> None:
        """Clean up after test."""
        # No cleanup needed for in-memory database
        pass


@pytest.mark.integration
class TestUniverseStorePITSafety:
    """
    Tests for PIT safety in UniverseStore.

    PIT (Pipeline Integration Tests) - tests complete data ingestion flow.
    These tests require more resources and time than unit tests.
    """

    @pytest.fixture(autouse=True)
    def setup(self, sqlite_client: SQLiteClient) -> None:
        """使用 fixture 自动注入已初始化的数据库客户端."""
        self.client = sqlite_client
        self.store = UniverseStore(self.client)

    def _create_securities(self, instrument_ids: list[int]) -> None:
        """Helper to create instrument records for testing."""
        for instrument_id in instrument_ids:
            self.client.execute(
                """INSERT INTO instrument
                (instrument_id, symbol, name, exchange, asset_class, list_date)
                VALUES (?, ?, ?, ?, ?, ?)""",
                [
                    instrument_id,
                    f"TEST{instrument_id}",
                    "Test",
                    "SSE",
                    "stock",
                    "2020-01-01",
                ],
            )
        self.client.commit()

    def test_pit_query_effective_boundary(self) -> None:
        """Test PIT query boundary conditions."""
        # Create universe
        self.store.create_universe("test_u", "Test", universe_type="custom")

        self._create_securities([100000001])

        # Add constituent with exact effective dates
        records = [
            {
                "instrument_id": 100000001,
                "effective_from": "2020-01-01",
                "effective_to": "2020-12-31",
                "weight": 1.0,
            },
        ]
        self.store.add_constituents("test_u", records)

        # Query on exact effective_from - should be included
        instrument_ids = self.store.get_constituent_instrument_ids(
            "test_u", asof="2020-01-01"
        )
        assert 100000001 in instrument_ids

        # Query on exact effective_to - should NOT be included
        # (effective_to is exclusive)
        instrument_ids = self.store.get_constituent_instrument_ids(
            "test_u", asof="2020-12-31"
        )
        assert 100000001 not in instrument_ids

    def test_pit_query_future_date(self) -> None:
        """Test PIT query with future date returns current."""
        # Create universe
        self.store.create_universe("test_u", "Test", universe_type="custom")

        self._create_securities([100000001])

        # Add constituent
        records = [
            {"instrument_id": 100000001, "effective_from": "2020-01-01", "weight": 1.0},
        ]
        self.store.add_constituents("test_u", records)

        # Query with future date
        instrument_ids = self.store.get_constituent_instrument_ids(
            "test_u", asof="2099-12-31"
        )
        assert 100000001 in instrument_ids

    def test_pit_query_before_effective_from(self) -> None:
        """Test PIT query before effective_from returns empty."""
        # Create universe
        self.store.create_universe("test_u", "Test", universe_type="custom")

        self._create_securities([100000001])

        # Add constituent
        records = [
            {"instrument_id": 100000001, "effective_from": "2020-01-01", "weight": 1.0},
        ]
        self.store.add_constituents("test_u", records)

        # Query before effective date
        instrument_ids = self.store.get_constituent_instrument_ids(
            "test_u", asof="2019-12-31"
        )
        assert len(instrument_ids) == 0
