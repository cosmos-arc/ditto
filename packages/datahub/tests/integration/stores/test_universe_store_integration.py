"""Integration tests for UniverseStore (SQLite seam)."""

import sqlite3

import pytest
from ditto_datahub.stores.sqlite_client import SQLiteClient
from ditto_datahub.stores.universe_store import UniverseStore
from ditto_foundation import SQLitePool


@pytest.mark.integration
class TestUniverseStoreIntegration:
    """Tests for UniverseStore integration with SQLite."""

    @pytest.fixture
    def pool(self) -> SQLitePool:
        """Create in-memory SQLite pool for testing."""
        return SQLitePool(db_path=":memory:")

    @pytest.fixture
    def client(self, pool: SQLitePool) -> SQLiteClient:
        """Create SQLite client with test schema."""
        client = SQLiteClient(pool)

        # Create test schema
        schema_sql = """
            CREATE TABLE universe (
                universe_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT,
                universe_type TEXT NOT NULL DEFAULT 'custom',
                source_ref TEXT
            );

            CREATE TABLE universe_constituent (
                universe_id TEXT NOT NULL,
                sid INTEGER NOT NULL,
                effective_from TEXT NOT NULL,
                effective_to TEXT,
                weight REAL DEFAULT 1.0,
                source TEXT,
                src_code TEXT,
                PRIMARY KEY (universe_id, sid, effective_from),
                FOREIGN KEY (universe_id) REFERENCES universe(universe_id)
            );

            CREATE INDEX idx_universe_type ON universe(universe_type);
            CREATE INDEX idx_universe_constituent_universe
                ON universe_constituent(universe_id);
        """
        client.executescript(schema_sql)
        return client

    @pytest.fixture
    def store(self, client: SQLiteClient) -> UniverseStore:
        """Create UniverseStore instance."""
        return UniverseStore(client)

    def test_create_universe(self, store: UniverseStore) -> None:
        """Test creating a new universe."""
        store.create_universe(
            universe_id="csi300",
            name="沪深300指数",
            description="沪深300指数成分股",
            universe_type="index",
            source_ref="000300.SH",
        )

        # Verify universe was created
        row = store.get_universe("csi300")
        assert row is not None
        assert row["universe_id"] == "csi300"
        assert row["name"] == "沪深300指数"
        assert row["universe_type"] == "index"
        assert row["source_ref"] == "000300.SH"

    def test_create_universe_duplicate_raises_error(self, store: UniverseStore) -> None:
        """Test creating duplicate universe raises error."""
        store.create_universe(
            universe_id="test_universe",
            name="测试",
        )

        # Should raise IntegrityError on duplicate
        with pytest.raises(sqlite3.IntegrityError):
            store.create_universe(
                universe_id="test_universe",
                name="测试重复",
            )

    def test_get_universe_not_found(self, store: UniverseStore) -> None:
        """Test getting non-existent universe returns None."""
        row = store.get_universe("nonexistent")
        assert row is None

    def test_list_universes(self, store: UniverseStore) -> None:
        """Test listing all universes."""
        store.create_universe(
            universe_id="csi300",
            name="沪深300",
            universe_type="index",
        )
        store.create_universe(
            universe_id="csi500",
            name="中证500",
            universe_type="index",
        )
        store.create_universe(
            universe_id="custom_stocks",
            name="自定义股票池",
            universe_type="custom",
        )

        # List all universes
        all_universes = store.list_universes()
        assert len(all_universes) == 3

        # Filter by type
        index_universes = store.list_universes(universe_type="index")
        assert len(index_universes) == 2

        custom_universes = store.list_universes(universe_type="custom")
        assert len(custom_universes) == 1

    def test_add_constituents(self, store: UniverseStore) -> None:
        """Test adding constituents to a universe."""
        store.create_universe(
            universe_id="test_universe",
            name="测试",
        )

        records = [
            {
                "sid": 1_000_001,
                "effective_from": "2024-01-01",
                "weight": 0.5,
                "source": "tushare",
                "src_code": "600000.SH",
            },
            {
                "sid": 1_000_002,
                "effective_from": "2024-01-01",
                "weight": 0.5,
                "source": "tushare",
                "src_code": "600001.SH",
            },
        ]

        count = store.add_constituents("test_universe", records)
        assert count == 2

    def test_get_constituents_current(self, store: UniverseStore) -> None:
        """Test getting current constituents."""
        store.create_universe(
            universe_id="test_universe",
            name="测试",
        )

        records = [
            {"sid": 1_000_001, "effective_from": "2024-01-01", "weight": 0.5},
            {"sid": 1_000_002, "effective_from": "2024-01-01", "weight": 0.5},
        ]

        store.add_constituents("test_universe", records)

        # Get current constituents
        constituents = store.get_constituents("test_universe")
        assert len(constituents) == 2
        assert constituents["sid"].to_list() == [1_000_001, 1_000_002]

    def test_get_constituents_pit(self, store: UniverseStore) -> None:
        """Test getting constituents with PIT."""
        store.create_universe(
            universe_id="test_universe",
            name="测试",
        )

        records = [
            {
                "sid": 1_000_001,
                "effective_from": "2024-01-01",
                "effective_to": "2024-06-01",
                "weight": 0.5,
            },
            {
                "sid": 1_000_002,
                "effective_from": "2024-01-01",
                "weight": 0.5,
            },
            {
                "sid": 1_000_003,
                "effective_from": "2024-06-01",
                "weight": 0.5,
            },
        ]

        store.add_constituents("test_universe", records)

        # Get constituents as of 2024-03-01 (sid 1 and 2)
        constituents_mar = store.get_constituents("test_universe", asof="2024-03-01")
        assert len(constituents_mar) == 2
        assert set(constituents_mar["sid"].to_list()) == {
            1_000_001,
            1_000_002,
        }

        # Get constituents as of 2024-07-01 (sid 2 and 3)
        constituents_jul = store.get_constituents("test_universe", asof="2024-07-01")
        assert len(constituents_jul) == 2
        assert set(constituents_jul["sid"].to_list()) == {
            1_000_002,
            1_000_003,
        }

    def test_get_constituents_sids(self, store: UniverseStore) -> None:
        """Test getting constituent SIDs as list."""
        store.create_universe(
            universe_id="test_universe",
            name="测试",
        )

        records = [
            {"sid": 1_000_001, "effective_from": "2024-01-01"},
            {"sid": 1_000_002, "effective_from": "2024-01-01"},
        ]

        store.add_constituents("test_universe", records)

        sids = store.get_constituents_sids("test_universe")
        assert sids == [1_000_001, 1_000_002]

    def test_remove_constituent(self, store: UniverseStore) -> None:
        """Test removing a constituent."""
        store.create_universe(
            universe_id="test_universe",
            name="测试",
        )

        records = [
            {"sid": 1_000_001, "effective_from": "2024-01-01"},
            {"sid": 1_000_002, "effective_from": "2024-01-01"},
        ]

        store.add_constituents("test_universe", records)

        # Remove first constituent
        store.remove_constituent("test_universe", 1_000_001, "2024-06-01")

        # Verify only second constituent remains
        constituents = store.get_constituents("test_universe")
        assert len(constituents) == 1
        assert constituents["sid"][0] == 1_000_002

    def test_remove_constituent_sets_effective_to(self, store: UniverseStore) -> None:
        """Test that remove_constituent sets effective_to."""
        store.create_universe(
            universe_id="test_universe",
            name="测试",
        )

        records = [
            {"sid": 1_000_001, "effective_from": "2024-01-01"},
        ]

        store.add_constituents("test_universe", records)
        store.remove_constituent("test_universe", 1_000_001, "2024-06-01")

        # Verify effective_to was set
        row = store._client.fetchone(
            """SELECT * FROM universe_constituent
            WHERE universe_id = ? AND sid = ?""",
            ["test_universe", 1_000_001],
        )
        assert row is not None
        assert row["effective_to"] == "2024-06-01"

    def test_get_constituents_empty_universe(self, store: UniverseStore) -> None:
        """Test getting constituents from empty universe."""
        store.create_universe(
            universe_id="empty_universe",
            name="空池子",
        )

        constituents = store.get_constituents("empty_universe")
        assert constituents.is_empty()

        sids = store.get_constituents_sids("empty_universe")
        assert sids == []
