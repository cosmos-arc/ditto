"""Tests for IndexWeightStore."""

import pytest
from ditto_datahub.stores.index_weight_store import IndexWeightStore
from ditto_datahub.stores.sqlite_client import SQLiteClient
from ditto_foundation import SQLitePool


@pytest.mark.pit
class TestIndexWeightStore:
    """Tests for IndexWeightStore.

    PIT (Pipeline Integration Tests) - tests complete data ingestion flow.
    These tests require more resources and time than unit tests.
    """

    def setup_method(self) -> None:
        """Set up test database."""
        # Create in-memory database for testing
        self.pool = SQLitePool(":memory:")
        self.pool.init_schema()
        self.client = SQLiteClient(self.pool)
        self.store = IndexWeightStore(self.client)

    def test_index_weight_store_init(self) -> None:
        """Test IndexWeightStore initialization."""
        assert self.store._client is not None

    def test_upsert_weights(self) -> None:
        """Test upserting index constituent weights."""
        records = [
            {"sid": 1000001, "effective_from": "2024-01-01", "weight": 0.5},
            {"sid": 1000002, "effective_from": "2024-01-01", "weight": 0.3},
            {"sid": 1000003, "effective_from": "2024-01-01", "weight": 0.2},
        ]

        count = self.store.upsert_weights("000300.SH", records)
        assert count == 3

        # Verify data was inserted
        constituents = self.store.get_constituents("000300.SH")
        assert len(constituents) == 3
        assert sorted(constituents["sid"].to_list()) == [
            1000001,
            1000002,
            1000003,
        ]

    def test_upsert_weights_with_effective_to(self) -> None:
        """Test upserting with effective_to date (expired constituent)."""
        records = [
            {
                "sid": 1000001,
                "effective_from": "2024-01-01",
                "effective_to": "2024-06-30",
                "weight": 0.5,
            },
        ]

        count = self.store.upsert_weights("000300.SH", records)
        assert count == 1

        # Current query should return empty (constituent expired)
        constituents = self.store.get_constituents("000300.SH")
        assert constituents.is_empty()

        # But historical query should return it
        historical = self.store.get_constituents("000300.SH", asof="2024-01-15")
        assert len(historical) == 1
        assert historical["effective_to"][0] == "2024-06-30"

    def test_get_constituents_current(self) -> None:
        """Test getting current constituents (asof=None)."""
        records = [
            {"sid": 1000001, "effective_from": "2024-01-01", "weight": 0.5},
            {"sid": 1000002, "effective_from": "2024-01-01", "weight": 0.3},
            {
                "sid": 1000003,
                "effective_from": "2024-01-01",
                "effective_to": "2024-06-30",
                "weight": 0.2,
            },
        ]
        self.store.upsert_weights("000300.SH", records)

        # Get current constituents (should exclude expired ones)
        constituents = self.store.get_constituents("000300.SH")
        assert len(constituents) == 2
        assert 1000001 in constituents["sid"].to_list()
        assert 1000002 in constituents["sid"].to_list()
        assert 1000003 not in constituents["sid"].to_list()

    def test_get_constituents_with_asof(self) -> None:
        """Test PIT query with asof parameter."""
        records = [
            {
                "sid": 1000001,
                "effective_from": "2024-01-01",
                "effective_to": "2024-06-30",
                "weight": 0.5,
            },
            {"sid": 1000002, "effective_from": "2024-01-01", "weight": 0.3},
            {
                "sid": 1000003,
                "effective_from": "2024-07-01",
                "weight": 0.2,
            },
        ]
        self.store.upsert_weights("000300.SH", records)

        # Query as of 2024-01-15 (before first change)
        constituents_jan = self.store.get_constituents("000300.SH", asof="2024-01-15")
        assert len(constituents_jan) == 2
        assert 1000001 in constituents_jan["sid"].to_list()
        assert 1000002 in constituents_jan["sid"].to_list()
        assert 1000003 not in constituents_jan["sid"].to_list()

        # Query as of 2024-07-15 (after change)
        constituents_jul = self.store.get_constituents("000300.SH", asof="2024-07-15")
        assert len(constituents_jul) == 2
        assert 1000001 not in constituents_jul["sid"].to_list()  # expired
        assert 1000002 in constituents_jul["sid"].to_list()
        assert 1000003 in constituents_jul["sid"].to_list()

    def test_get_constituents_empty_result(self) -> None:
        """Test getting constituents for non-existent index."""
        constituents = self.store.get_constituents("nonexistent")
        assert constituents.is_empty()

    def test_get_constituents_sids(self) -> None:
        """Test getting constituent sids as list."""
        records = [
            {"sid": 1000001, "effective_from": "2024-01-01", "weight": 0.5},
            {"sid": 1000002, "effective_from": "2024-01-01", "weight": 0.3},
        ]
        self.store.upsert_weights("000300.SH", records)

        sids = self.store.get_constituents_sids("000300.SH")
        assert len(sids) == 2
        assert 1000001 in sids
        assert 1000002 in sids

    def test_get_constituents_sids_with_asof(self) -> None:
        """Test getting constituent sids with PIT query."""
        records = [
            {
                "sid": 1000001,
                "effective_from": "2024-01-01",
                "effective_to": "2024-06-30",
                "weight": 0.5,
            },
            {"sid": 1000002, "effective_from": "2024-01-01", "weight": 0.3},
        ]
        self.store.upsert_weights("000300.SH", records)

        # Get sids as of 2024-01-15
        sids_jan = self.store.get_constituents_sids("000300.SH", asof="2024-01-15")
        assert len(sids_jan) == 2

        # Get sids as of 2024-07-01
        sids_jul = self.store.get_constituents_sids("000300.SH", asof="2024-07-01")
        assert len(sids_jul) == 1
        assert 1000002 in sids_jul

    def test_remove_constituent(self) -> None:
        """Test removing a constituent by setting effective_to."""
        records = [
            {"sid": 1000001, "effective_from": "2024-01-01", "weight": 0.5},
            {"sid": 1000002, "effective_from": "2024-01-01", "weight": 0.3},
        ]
        self.store.upsert_weights("000300.SH", records)

        # Remove one constituent
        self.store.remove_constituent("000300.SH", 1000001, "2024-06-30")

        # Verify it's no longer in current constituents
        current_sids = self.store.get_constituents_sids("000300.SH")
        assert 1000001 not in current_sids
        assert 1000002 in current_sids

        # But it should be in historical query before removal date
        historical_sids = self.store.get_constituents_sids(
            "000300.SH", asof="2024-01-15"
        )
        assert 1000001 in historical_sids

    def test_upsert_update_existing(self) -> None:
        """Test upsert updates existing records."""
        # First insert
        records = [
            {"sid": 1000001, "effective_from": "2024-01-01", "weight": 0.5},
        ]
        self.store.upsert_weights("000300.SH", records)

        # Update with same primary key
        records_update = [
            {"sid": 1000001, "effective_from": "2024-01-01", "weight": 0.8},
        ]
        self.store.upsert_weights("000300.SH", records_update)

        # Verify weight was updated
        constituents = self.store.get_constituents("000300.SH")
        assert constituents["weight"][0] == 0.8

    def test_upsert_multiple_indices(self) -> None:
        """Test upserting for multiple indices."""
        records_300 = [
            {"sid": 1000001, "effective_from": "2024-01-01", "weight": 0.5},
        ]
        records_500 = [
            {"sid": 1000002, "effective_from": "2024-01-01", "weight": 0.3},
        ]

        self.store.upsert_weights("000300.SH", records_300)
        self.store.upsert_weights("000905.SH", records_500)

        # Verify both indices have correct constituents
        sids_300 = self.store.get_constituents_sids("000300.SH")
        sids_500 = self.store.get_constituents_sids("000905.SH")

        assert sids_300 == [1000001]
        assert sids_500 == [1000002]


@pytest.mark.pit
class TestIndexWeightStorePITSafety:
    """Tests for PIT safety in IndexWeightStore.

    PIT (Pipeline Integration Tests) - tests complete data ingestion flow.
    These tests require more resources and time than unit tests.
    """

    def setup_method(self) -> None:
        """Set up test database."""
        self.pool = SQLitePool(":memory:")
        self.pool.init_schema()
        self.client = SQLiteClient(self.pool)
        self.store = IndexWeightStore(self.client)

    def test_pit_query_effective_boundary(self) -> None:
        """Test PIT query boundary conditions."""
        records = [
            {
                "sid": 1000001,
                "effective_from": "2024-01-01",
                "effective_to": "2024-12-31",
                "weight": 0.5,
            },
        ]
        self.store.upsert_weights("000300.SH", records)

        # Query on exact effective_from - should be included
        sids = self.store.get_constituents_sids("000300.SH", asof="2024-01-01")
        assert 1000001 in sids

        # Query on exact effective_to - should NOT be included
        # (effective_to is exclusive)
        sids = self.store.get_constituents_sids("000300.SH", asof="2024-12-31")
        assert 1000001 not in sids

    def test_pit_query_future_date(self) -> None:
        """Test PIT query with future date returns current."""
        records = [
            {"sid": 1000001, "effective_from": "2024-01-01", "weight": 0.5},
        ]
        self.store.upsert_weights("000300.SH", records)

        # Query with future date
        sids = self.store.get_constituents_sids("000300.SH", asof="2099-12-31")
        assert 1000001 in sids

    def test_pit_query_before_effective_from(self) -> None:
        """Test PIT query before effective_from returns empty."""
        records = [
            {"sid": 1000001, "effective_from": "2024-01-01", "weight": 0.5},
        ]
        self.store.upsert_weights("000300.SH", records)

        # Query before effective date
        sids = self.store.get_constituents_sids("000300.SH", asof="2023-12-31")
        assert len(sids) == 0

    def test_pit_query_with_null_effective_to(self) -> None:
        """Test PIT query with null effective_to (current constituent)."""
        records = [
            {"sid": 1000001, "effective_from": "2024-01-01", "weight": 0.5},
        ]
        self.store.upsert_weights("000300.SH", records)

        # Query after effective date - should be included (no effective_to)
        sids = self.store.get_constituents_sids("000300.SH", asof="2024-06-01")
        assert 1000001 in sids

    def teardown_method(self) -> None:
        """Clean up after test."""
        # No cleanup needed for in-memory database
        pass
