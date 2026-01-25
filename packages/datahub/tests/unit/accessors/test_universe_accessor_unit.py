"""Tests for UniverseAccessor."""

import polars as pl
import pytest
from ditto_datahub.accessors.universe_accessor import UniverseAccessor
from ditto_datahub.runtime.sid_allocator import SidAllocator
from ditto_datahub.stores.security_store import SecurityStore
from ditto_datahub.stores.sqlite_client import SQLiteClient
from ditto_datahub.stores.universe_store import UniverseStore
from ditto_foundation import SQLitePool


@pytest.mark.integration
class TestUniverseAccessor:
    """
    Tests for UniverseAccessor.

    PIT (Pipeline Integration Tests) - tests complete data ingestion flow.
    These tests require more resources and time than unit tests.
    """

    @pytest.fixture(autouse=True)
    def setup(self, sqlite_client: SQLiteClient, sqlite_pool: SQLitePool) -> None:
        """使用 fixture 自动注入已初始化的数据库客户端和连接池."""
        self.pool = sqlite_pool
        self.client = sqlite_client
        self.universe_store = UniverseStore(self.client)
        self.security_store = SecurityStore(self.client)
        self.sid_allocator = SidAllocator(self.pool)
        self.accessor = UniverseAccessor(
            self.universe_store,
            self.security_store,
            self.sid_allocator,
        )

    def _create_securities(self, sids: list[int]) -> None:
        """Helper to create security records for testing."""
        for sid in sids:
            self.client.execute(
                """INSERT INTO security
                (sid, symbol, name, exchange, asset_class, list_date)
                VALUES (?, ?, ?, ?, ?, ?)""",
                [sid, f"TEST{sid}", "Test", "SSE", "stock", "2020-01-01"],
            )
        self.client.commit()

    def test_accessor_init(self) -> None:
        """Test UniverseAccessor initialization."""
        assert self.accessor._universe_store is not None
        assert self.accessor._sid_allocator is not None

    def test_create_universe(self) -> None:
        """Test creating a universe."""
        # Act
        self.accessor.create(
            universe_id="test_universe",
            name="Test Universe",
            description="Test universe for unit testing",
            universe_type="custom",
            source_ref=None,
        )

        # Assert
        result = self.universe_store.get_universe("test_universe")
        assert result is not None
        assert result["universe_id"] == "test_universe"
        assert result["name"] == "Test Universe"
        assert result["universe_type"] == "custom"

    def test_create_universe_with_source_ref(self) -> None:
        """Test creating a universe with source reference."""
        # Act
        self.accessor.create(
            universe_id="index_300",
            name="CSI 300 Index",
            description="CSI 300 Index Universe",
            universe_type="index",
            source_ref="000300.SH",
        )

        # Assert
        result = self.universe_store.get_universe("index_300")
        assert result is not None
        assert result["source_ref"] == "000300.SH"
        assert result["universe_type"] == "index"

    def test_get_constituents_basic(self) -> None:
        """Test getting constituents without symbol."""
        # Arrange
        self.accessor.create("test_u", "Test", "custom")
        self._create_securities([100000001, 100000002])

        records = [
            {"sid": 100000001, "effective_from": "2020-01-01", "weight": 1.0},
            {"sid": 100000002, "effective_from": "2020-01-01", "weight": 1.0},
        ]
        self.universe_store.add_constituents("test_u", records)

        # Act
        constituents = self.accessor.get_constituents(
            "test_u", asof=None, with_symbol=False
        )

        # Assert
        assert len(constituents) == 2
        assert "sid" in constituents.columns
        assert "symbol" not in constituents.columns

    def test_get_constituents_with_symbol(self) -> None:
        """Test getting constituents with symbol join."""
        # Arrange
        self.accessor.create("test_u", "Test", "custom")
        self._create_securities([100000001, 100000002])

        records = [
            {"sid": 100000001, "effective_from": "2020-01-01", "weight": 1.0},
            {"sid": 100000002, "effective_from": "2020-01-01", "weight": 1.0},
        ]
        self.universe_store.add_constituents("test_u", records)

        # Act
        constituents = self.accessor.get_constituents(
            "test_u", asof=None, with_symbol=True
        )

        # Assert
        assert len(constituents) == 2
        assert "sid" in constituents.columns
        assert "symbol" in constituents.columns
        assert "TEST100000001" in constituents["symbol"].to_list()
        assert "TEST100000002" in constituents["symbol"].to_list()

    def test_get_constituents_with_asof(self) -> None:
        """Test getting constituents with PIT asof query."""
        # Arrange
        self.accessor.create("test_u", "Test", "custom")
        self._create_securities([100000001, 100000002, 100000003])

        records = [
            {
                "sid": 100000001,
                "effective_from": "2020-01-01",
                "effective_to": "2021-06-30",
                "weight": 1.0,
            },
            {
                "sid": 100000002,
                "effective_from": "2020-01-01",
                "weight": 1.0,
            },
            {
                "sid": 100000003,
                "effective_from": "2021-07-01",
                "weight": 1.0,
            },
        ]
        self.universe_store.add_constituents("test_u", records)

        # Act - query as of 2021-01-01
        constituents = self.accessor.get_constituents(
            "test_u", asof="2021-01-01", with_symbol=False
        )

        # Assert
        assert len(constituents) == 2
        assert 100000001 in constituents["sid"].to_list()
        assert 100000002 in constituents["sid"].to_list()
        assert 100000003 not in constituents["sid"].to_list()

    def test_add_constituents_with_weights(self) -> None:
        """Test adding constituents with weights."""
        # Arrange
        self.accessor.create("test_u", "Test", "custom")
        self._create_securities([100000001, 100000002])

        # Act
        count = self.accessor.add_constituents(
            universe_id="test_u",
            sids=[100000001, 100000002],
            effective_date="2020-01-01",
            weights=[1.0, 0.5],
        )

        # Assert
        assert count == 2
        constituents = self.universe_store.get_constituents("test_u")
        assert len(constituents) == 2
        assert 1.0 in constituents["weight"].to_list()
        assert 0.5 in constituents["weight"].to_list()

    def test_add_constituents_default_weights(self) -> None:
        """Test adding constituents without weights (default 1.0)."""
        # Arrange
        self.accessor.create("test_u", "Test", "custom")
        self._create_securities([100000001, 100000002])

        # Act
        count = self.accessor.add_constituents(
            universe_id="test_u",
            sids=[100000001, 100000002],
            effective_date="2020-01-01",
            weights=None,
        )

        # Assert
        assert count == 2
        constituents = self.universe_store.get_constituents("test_u")
        assert all(constituents["weight"] == 1.0)

    def test_list_universes(self) -> None:
        """Test listing all universes."""
        # Arrange
        self.accessor.create(
            "universe1", "Universe 1", description="U1", universe_type="custom"
        )
        self.accessor.create(
            "universe2", "Universe 2", description="U2", universe_type="index"
        )
        self.accessor.create(
            "universe3", "Universe 3", description="U3", universe_type="custom"
        )

        # Act
        universes = self.accessor.list_universes(universe_type=None)

        # Assert
        assert len(universes) == 3
        assert "universe1" in universes["universe_id"].to_list()
        assert "universe2" in universes["universe_id"].to_list()
        assert "universe3" in universes["universe_id"].to_list()

    def test_list_universes_with_filter(self) -> None:
        """Test listing universes with type filter."""
        # Arrange
        self.accessor.create(
            "custom1", "Custom 1", description="Custom 1", universe_type="custom"
        )
        self.accessor.create(
            "index1", "Index 1", description="Index 1", universe_type="index"
        )
        self.accessor.create(
            "custom2", "Custom 2", description="Custom 2", universe_type="custom"
        )

        # Act
        custom_universes = self.accessor.list_universes(universe_type="custom")

        # Assert
        assert len(custom_universes) == 2
        assert all(custom_universes["universe_type"] == "custom")

    def test_get_csi300_returns_sids(self) -> None:
        """Test get_csi300 predefined universe shortcut."""
        # Arrange - Create CSI300 universe
        self.accessor.create(
            universe_id="csi300",
            name="CSI 300",
            description="CSI 300 Index",
            universe_type="index",
            source_ref="000300.SH",
        )
        self._create_securities([100000001, 100000002, 100000003])

        records = [
            {"sid": 100000001, "effective_from": "2020-01-01", "weight": 1.0},
            {"sid": 100000002, "effective_from": "2020-01-01", "weight": 1.0},
            {"sid": 100000003, "effective_from": "2020-01-01", "weight": 1.0},
        ]
        self.universe_store.add_constituents("csi300", records)

        # Act
        sids = self.accessor.get_csi300(asof=None)

        # Assert
        assert len(sids) == 3
        assert 100000001 in sids
        assert 100000002 in sids
        assert 100000003 in sids

    def test_get_csi300_with_asof(self) -> None:
        """Test get_csi300 with PIT query."""
        # Arrange - Create CSI300 universe with changes
        self.accessor.create(
            universe_id="csi300",
            name="CSI 300",
            description="CSI 300 Index",
            universe_type="index",
            source_ref="000300.SH",
        )
        self._create_securities([100000001, 100000002, 100000003])

        records = [
            {
                "sid": 100000001,
                "effective_from": "2020-01-01",
                "effective_to": "2021-06-30",
                "weight": 1.0,
            },
            {
                "sid": 100000002,
                "effective_from": "2020-01-01",
                "weight": 1.0,
            },
            {
                "sid": 100000003,
                "effective_from": "2021-07-01",
                "weight": 1.0,
            },
        ]
        self.universe_store.add_constituents("csi300", records)

        # Act - query as of 2021-01-01
        sids = self.accessor.get_csi300(asof="2021-01-01")

        # Assert
        assert len(sids) == 2
        assert 100000001 in sids
        assert 100000002 in sids
        assert 100000003 not in sids

    def test_get_csi500_returns_sids(self) -> None:
        """Test get_csi500 predefined universe shortcut."""
        # Arrange - Create CSI500 universe
        self.accessor.create(
            universe_id="csi500",
            name="CSI 500",
            description="CSI 500 Index",
            universe_type="index",
            source_ref="000905.SH",
        )
        self._create_securities([100000001, 100000002])

        records = [
            {"sid": 100000001, "effective_from": "2020-01-01", "weight": 1.0},
            {"sid": 100000002, "effective_from": "2020-01-01", "weight": 1.0},
        ]
        self.universe_store.add_constituents("csi500", records)

        # Act
        sids = self.accessor.get_csi500(asof=None)

        # Assert
        assert len(sids) == 2
        assert 100000001 in sids
        assert 100000002 in sids

    def test_get_csi500_with_asof(self) -> None:
        """Test get_csi500 with PIT query."""
        # Arrange - Create CSI500 universe
        self.accessor.create(
            universe_id="csi500",
            name="CSI 500",
            description="CSI 500 Index",
            universe_type="index",
            source_ref="000905.SH",
        )
        self._create_securities([100000001, 100000002])

        records = [
            {
                "sid": 100000001,
                "effective_from": "2020-01-01",
                "effective_to": "2021-06-30",
                "weight": 1.0,
            },
            {
                "sid": 100000002,
                "effective_from": "2020-01-01",
                "weight": 1.0,
            },
        ]
        self.universe_store.add_constituents("csi500", records)

        # Act - query as of 2021-07-01
        sids = self.accessor.get_csi500(asof="2021-07-01")

        # Assert
        assert len(sids) == 1
        assert 100000002 in sids

    def teardown_method(self) -> None:
        """Clean up after test."""
        # No cleanup needed for in-memory database
        pass


class TestUniverseAccessorWithMocks:
    """Tests for UniverseAccessor with mocked dependencies."""

    def test_add_constituents_with_mocks(self, mocker) -> None:
        """Test add_constituents with mocked store and allocator."""
        # Arrange
        mock_store = mocker.Mock()
        mock_security_store = mocker.Mock()
        mock_allocator = mocker.Mock()
        repo = UniverseAccessor(mock_store, mock_security_store, mock_allocator)

        mock_store.add_constituents.return_value = 2

        # Act
        count = repo.add_constituents(
            universe_id="test_u",
            sids=[100000001, 100000002],
            effective_date="2020-01-01",
            weights=[1.0, 0.5],
        )

        # Assert
        assert count == 2
        mock_store.add_constituents.assert_called_once()
        call_args = mock_store.add_constituents.call_args
        assert call_args[0][0] == "test_u"
        assert len(call_args[0][1]) == 2

    def test_get_constituents_with_mock_store(self, mocker) -> None:
        """Test get_constituents with mocked store."""
        # Arrange
        mock_store = mocker.Mock()
        mock_security_store = mocker.Mock()
        mock_allocator = mocker.Mock()
        repo = UniverseAccessor(mock_store, mock_security_store, mock_allocator)

        # Mock return data
        mock_df = pl.DataFrame(
            {
                "sid": [100000001, 100000002],
                "effective_from": ["2020-01-01", "2020-01-01"],
                "weight": [1.0, 1.0],
            }
        )
        mock_store.get_constituents.return_value = mock_df

        # Act
        result = repo.get_constituents("test_u", asof=None, with_symbol=False)

        # Assert
        assert len(result) == 2
        mock_store.get_constituents.assert_called_once_with(
            universe_id="test_u", asof=None
        )

    def test_create_with_mock_store(self, mocker) -> None:
        """Test create with mocked store."""
        # Arrange
        mock_store = mocker.Mock()
        mock_security_store = mocker.Mock()
        mock_allocator = mocker.Mock()
        repo = UniverseAccessor(mock_store, mock_security_store, mock_allocator)

        # Act
        repo.create(
            universe_id="test_u",
            name="Test",
            description="Test universe",
            universe_type="custom",
            source_ref=None,
        )

        # Assert
        mock_store.create_universe.assert_called_once_with(
            universe_id="test_u",
            name="Test",
            description="Test universe",
            universe_type="custom",
            source_ref=None,
        )

    def test_list_universes_with_mock_store(self, mocker) -> None:
        """Test list_universes with mocked store."""
        # Arrange
        mock_store = mocker.Mock()
        mock_security_store = mocker.Mock()
        mock_allocator = mocker.Mock()
        repo = UniverseAccessor(mock_store, mock_security_store, mock_allocator)

        mock_df = pl.DataFrame(
            {
                "universe_id": ["u1", "u2"],
                "name": ["Universe 1", "Universe 2"],
                "universe_type": ["custom", "index"],
            }
        )
        mock_store.list_universes.return_value = mock_df

        # Act
        result = repo.list_universes(universe_type=None)

        # Assert
        assert len(result) == 2
        mock_store.list_universes.assert_called_once_with(universe_type=None)


class TestUniverseAccessorSecurityDependency:
    """Tests for UniverseAccessor security store dependency injection."""

    def test_init_requires_security_store(self) -> None:
        """Test UniverseAccessor requires security_store parameter."""
        # Arrange
        pool = SQLitePool(":memory:")
        pool.init_schema()
        client = SQLiteClient(pool)
        universe_store = UniverseStore(client)
        security_store = SecurityStore(client)
        sid_allocator = SidAllocator(pool)

        # Act & Assert - Should accept security_store
        repo = UniverseAccessor(
            universe_store=universe_store,
            security_store=security_store,
            sid_allocator=sid_allocator,
        )

        assert repo._universe_store is universe_store
        assert repo._security_store is security_store
        assert repo._sid_allocator is sid_allocator

    def test_get_constituents_with_symbol_uses_security_store(self, mocker) -> None:
        """Test get_constituents with_symbol=True uses SecurityStore."""
        # Arrange
        mock_universe_store = mocker.Mock()
        mock_security_store = mocker.Mock()
        mock_allocator = mocker.Mock()

        repo = UniverseAccessor(
            universe_store=mock_universe_store,
            security_store=mock_security_store,
            sid_allocator=mock_allocator,
        )

        constituents_df = pl.DataFrame(
            {
                "sid": [1, 2, 3],
                "weight": [1.0, 1.0, 1.0],
            }
        )
        enriched_df = pl.DataFrame(
            {
                "sid": [1, 2, 3],
                "weight": [1.0, 1.0, 1.0],
                "symbol": ["A", "B", "C"],
            }
        )

        mock_universe_store.get_constituents.return_value = constituents_df
        mock_security_store.enrich_with_symbol.return_value = enriched_df

        # Act
        result = repo.get_constituents("test_u", asof=None, with_symbol=True)

        # Assert
        mock_universe_store.get_constituents.assert_called_once_with(
            universe_id="test_u", asof=None
        )
        mock_security_store.enrich_with_symbol.assert_called_once_with(constituents_df)
        assert result.equals(enriched_df)
