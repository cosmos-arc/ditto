"""Integration tests for InstrumentStore (SQLite seam)."""

import polars as pl
import pytest
from ditto_datahub.stores.metadata.instrument import (
    InstrumentRegistration,
    InstrumentStore,
)
from ditto_datahub.stores.sqlite_client import SQLiteClient
from ditto_foundation import SQLitePool


@pytest.mark.integration
class TestInstrumentStoreIntegration:
    """Tests for InstrumentStore integration with SQLite."""

    @pytest.fixture
    def pool(self) -> SQLitePool:
        """Create in-memory SQLite pool for testing."""
        # Use :memory: database for testing
        return SQLitePool(db_path=":memory:")

    @pytest.fixture
    def client(self, pool: SQLitePool) -> SQLiteClient:
        """Create SQLite client with test schema."""
        client = SQLiteClient(pool)

        # Create test schema
        schema_sql = """
            CREATE TABLE instrument (
                instrument_id INTEGER PRIMARY KEY,
                symbol TEXT NOT NULL,
                name TEXT NOT NULL,
                exchange TEXT NOT NULL,
                board TEXT,
                asset_class TEXT NOT NULL,
                list_date TEXT NOT NULL,
                is_active BOOLEAN DEFAULT TRUE
            );

            CREATE TABLE instrument_mapping (
                instrument_id INTEGER NOT NULL,
                source TEXT NOT NULL,
                source_ticker TEXT NOT NULL,
                effective_from TEXT NOT NULL,
                effective_to TEXT,
                is_primary BOOLEAN DEFAULT TRUE,
                FOREIGN KEY (instrument_id) REFERENCES instrument(instrument_id)
            );

            CREATE INDEX idx_security_symbol ON instrument(symbol);
            CREATE INDEX idx_security_mapping_source_ticker
            ON instrument_mapping(source_ticker);
            CREATE INDEX idx_security_mapping_instrument_id
            ON instrument_mapping(instrument_id);
        """
        client.executescript(schema_sql)
        return client

    @pytest.fixture
    def store(self, client: SQLiteClient) -> InstrumentStore:
        """Create InstrumentStore instance."""
        return InstrumentStore(client)

    def test_register_new_security(self, store: InstrumentStore) -> None:
        """Test registering a new instrument."""

        registration = InstrumentRegistration(
            source_ticker="600000.SH",
            symbol="600000",
            name="浦发银行",
            exchange="SSE",
            asset_class="stock",
            list_date="1999-11-10",
        )

        instrument_id = store.register(1_000_001, registration)

        assert instrument_id == 1_000_001

        # Verify instrument table
        row = store._client.fetchone(
            "SELECT * FROM instrument WHERE instrument_id = ?", [instrument_id]
        )
        assert row is not None
        assert row["symbol"] == "600000"
        assert row["name"] == "浦发银行"

        # Verify mapping table
        mapping = store._client.fetchone(
            """SELECT * FROM instrument_mapping
            WHERE instrument_id = ? AND source_ticker = ?""",
            [instrument_id, "600000.SH"],
        )
        assert mapping is not None
        assert mapping["source"] == "tushare"

    def test_resolve_instrument_id_current(self, store: InstrumentStore) -> None:
        """Test resolving source_ticker to instrument_id (current)."""

        registration = InstrumentRegistration(
            source_ticker="600000.SH",
            symbol="600000",
            name="浦发银行",
            exchange="SSE",
            asset_class="stock",
            list_date="1999-11-10",
        )

        store.register(1_000_001, registration)

        # Resolve current
        instrument_id = store.resolve_instrument_id("600000.SH", "tushare", asof=None)
        assert instrument_id == 1_000_001

    def test_resolve_instrument_id_pit(self, store: InstrumentStore) -> None:
        """Test resolving source_ticker to instrument_id with PIT."""

        # Register first instrument
        registration1 = InstrumentRegistration(
            source_ticker="600000.SH",
            symbol="600000",
            name="浦发银行",
            exchange="SSE",
            asset_class="stock",
            list_date="1999-11-10",
        )
        store.register(1_000_001, registration1)

        # Simulate code change by updating effective_to
        store._client.execute(
            """UPDATE instrument_mapping
            SET effective_to = '2024-01-01'
            WHERE instrument_id = ? AND source_ticker = ?""",
            [1_000_001, "600000.SH"],
        )
        store._client.commit()

        # Register new mapping for same Instrument ID
        store._client.execute(
            """INSERT INTO instrument_mapping
            (instrument_id, source, source_ticker, effective_from, is_primary)
            VALUES (?, ?, ?, ?, TRUE)""",
            [1_000_001, "tushare", "600001.SH", "2024-01-01"],
        )
        store._client.commit()

        # Resolve with PIT date
        sid_before = store.resolve_instrument_id(
            "600000.SH", "tushare", asof="2023-12-31"
        )
        assert sid_before == 1_000_001

        sid_after = store.resolve_instrument_id(
            "600001.SH", "tushare", asof="2024-01-02"
        )
        assert sid_after == 1_000_001

    def test_resolve_instrument_id_not_found(self, store: InstrumentStore) -> None:
        """Test resolving non-existent source_ticker returns None."""
        instrument_id = store.resolve_instrument_id("INVALID.XYZ", "tushare", asof=None)
        assert instrument_id is None

    def test_resolve_instrument_ids_batch(self, store: InstrumentStore) -> None:
        """Test batch resolving source_tickers to instrument_ids."""

        # Register multiple securities
        for i, source_ticker in enumerate(["600000.SH", "600001.SH", "600002.SH"]):
            registration = InstrumentRegistration(
                source_ticker=source_ticker,
                symbol=f"60000{i}",
                name=f"测试{i}",
                exchange="SSE",
                asset_class="stock",
                list_date="1999-11-10",
            )
            store.register(1_000_001 + i, registration)

        # Batch resolve
        result = store.resolve_instrument_ids_batch(
            ["600000.SH", "600001.SH", "600002.SH", "INVALID.SH"],
            source="tushare",
        )

        assert len(result) == 3
        assert result["600000.SH"] == 1_000_001
        assert result["600001.SH"] == 1_000_002
        assert result["600002.SH"] == 1_000_003
        assert "INVALID.SH" not in result

    def test_resolve_by_symbol(self, store: InstrumentStore) -> None:
        """Test resolving by symbol."""

        registration = InstrumentRegistration(
            source_ticker="600000.SH",
            symbol="600000",
            name="浦发银行",
            exchange="SSE",
            asset_class="stock",
            list_date="1999-11-10",
        )
        store.register(1_000_001, registration)

        instrument_ids = store.resolve_by_symbol("600000", "tushare")
        assert len(instrument_ids) == 1
        assert instrument_ids[0] == 1_000_001

    def test_get_source_ticker(self, store: InstrumentStore) -> None:
        """Test reverse lookup: instrument_id to source_ticker."""

        registration = InstrumentRegistration(
            source_ticker="600000.SH",
            symbol="600000",
            name="浦发银行",
            exchange="SSE",
            asset_class="stock",
            list_date="1999-11-10",
        )
        store.register(1_000_001, registration)

        source_ticker = store.get_source_ticker(1_000_001, "tushare")
        assert source_ticker == "600000.SH"

    def test_get_by_sid(self, store: InstrumentStore) -> None:
        """Test getting instrument by instrument_id."""

        registration = InstrumentRegistration(
            source_ticker="600000.SH",
            symbol="600000",
            name="浦发银行",
            exchange="SSE",
            asset_class="stock",
            list_date="1999-11-10",
        )
        store.register(1_000_001, registration)

        row = store.get_by_instrument_id(1_000_001)
        assert row is not None
        assert row["instrument_id"] == 1_000_001
        assert row["symbol"] == "600000"
        assert row["name"] == "浦发银行"
        assert row["asset_class"] == "stock"

    def test_find_securities(self, store: InstrumentStore) -> None:
        """Test finding securities with filters."""

        # Register multiple securities
        registration1 = InstrumentRegistration(
            source_ticker="600000.SH",
            symbol="600000",
            name="浦发银行",
            exchange="SSE",
            asset_class="stock",
            list_date="1999-11-10",
        )
        store.register(1_000_001, registration1)

        registration2 = InstrumentRegistration(
            source_ticker="510300.SH",
            symbol="510300",
            name="沪深300ETF",
            exchange="SSE",
            asset_class="etf",
            list_date="2012-05-28",
        )
        store.register(2_000_001, registration2)

        # Find all stocks
        stocks = store.find_securities(asset_class="stock")
        assert len(stocks) == 1
        assert stocks["asset_class"][0] == "stock"

        # Find by exchange
        sse_securities = store.find_securities(exchange="SSE")
        assert len(sse_securities) == 2

    def test_list_sids(self, store: InstrumentStore) -> None:
        """Test listing instrument_ids with filters."""

        registration1 = InstrumentRegistration(
            source_ticker="600000.SH",
            symbol="600000",
            name="浦发银行",
            exchange="SSE",
            asset_class="stock",
            list_date="1999-11-10",
        )
        store.register(1_000_001, registration1)

        registration2 = InstrumentRegistration(
            source_ticker="510300.SH",
            symbol="510300",
            name="沪深300ETF",
            exchange="SSE",
            asset_class="etf",
            list_date="2012-05-28",
        )
        store.register(2_000_001, registration2)

        # List all instrument_ids
        all_sids = store.list_instrument_ids()
        assert len(all_sids) == 2

        # List only stocks
        stock_sids = store.list_instrument_ids(asset_class="stock")
        assert len(stock_sids) == 1
        assert stock_sids[0] == 1_000_001

    def test_get_symbol(self, store: InstrumentStore) -> None:
        """Test getting symbol by instrument_id."""

        registration = InstrumentRegistration(
            source_ticker="600000.SH",
            symbol="600000",
            name="浦发银行",
            exchange="SSE",
            asset_class="stock",
            list_date="1999-11-10",
        )
        store.register(1_000_001, registration)

        symbol = store.get_symbol(1_000_001)
        assert symbol == "600000"

    def test_get_instrument_id_symbol_map(self, store: InstrumentStore) -> None:
        """Test getting instrument_id to symbol mapping."""

        registration1 = InstrumentRegistration(
            source_ticker="600000.SH",
            symbol="600000",
            name="浦发银行",
            exchange="SSE",
            asset_class="stock",
            list_date="1999-11-10",
        )
        store.register(1_000_001, registration1)

        registration2 = InstrumentRegistration(
            source_ticker="600001.SH",
            symbol="600001",
            name="邯郸钢铁",
            exchange="SSE",
            asset_class="stock",
            list_date="1998-12-31",
        )
        store.register(1_000_002, registration2)

        # Get all mapping
        mapping = store.get_instrument_id_symbol_map()
        assert len(mapping) == 2
        assert mapping[1_000_001] == "600000"
        assert mapping[1_000_002] == "600001"

        # Get specific instrument_ids
        partial_mapping = store.get_instrument_id_symbol_map([1_000_001])
        assert len(partial_mapping) == 1
        assert partial_mapping[1_000_001] == "600000"

    def test_enrich_with_symbol(self, store: InstrumentStore) -> None:
        """Test enriching DataFrame with symbol column."""

        registration = InstrumentRegistration(
            source_ticker="600000.SH",
            symbol="600000",
            name="浦发银行",
            exchange="SSE",
            asset_class="stock",
            list_date="1999-11-10",
        )
        store.register(1_000_001, registration)

        # Create test DataFrame
        df = pl.DataFrame({"instrument_id": [1_000_001], "value": [100]})

        # Enrich with symbol
        enriched = store.enrich_with_symbol(df)

        assert "symbol" in enriched.columns
        assert enriched["symbol"][0] == "600000"
