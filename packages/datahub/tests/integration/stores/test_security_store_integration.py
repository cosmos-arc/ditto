"""Integration tests for SecurityStore (SQLite seam)."""

import polars as pl
import pytest
from ditto_datahub.stores.security_store import SecurityStore
from ditto_datahub.stores.sqlite_client import SQLiteClient
from ditto_foundation import SQLitePool


@pytest.mark.integration
class TestSecurityStoreIntegration:
    """Tests for SecurityStore integration with SQLite."""

    @pytest.fixture
    def pool(self) -> SQLitePool:
        """Create in-memory SQLite pool for testing."""
        # Use :memory: database for testing
        return SQLitePool(connection_string="file::memory:?cache=shared", pool_size=1)

    @pytest.fixture
    def client(self, pool: SQLitePool) -> SQLiteClient:
        """Create SQLite client with test schema."""
        client = SQLiteClient(pool)

        # Create test schema
        schema_sql = """
            CREATE TABLE security (
                sid INTEGER PRIMARY KEY,
                symbol TEXT NOT NULL,
                name TEXT NOT NULL,
                exchange TEXT NOT NULL,
                board TEXT,
                asset_class TEXT NOT NULL,
                list_date TEXT NOT NULL,
                is_active BOOLEAN DEFAULT TRUE
            );

            CREATE TABLE security_mapping (
                sid INTEGER NOT NULL,
                source TEXT NOT NULL,
                src_code TEXT NOT NULL,
                effective_from TEXT NOT NULL,
                effective_to TEXT,
                is_primary BOOLEAN DEFAULT TRUE,
                FOREIGN KEY (sid) REFERENCES security(sid)
            );

            CREATE INDEX idx_security_symbol ON security(symbol);
            CREATE INDEX idx_security_mapping_src_code ON security_mapping(src_code);
            CREATE INDEX idx_security_mapping_sid ON security_mapping(sid);
        """
        client.executescript(schema_sql)
        return client

    @pytest.fixture
    def store(self, client: SQLiteClient) -> SecurityStore:
        """Create SecurityStore instance."""
        return SecurityStore(client)

    def test_register_new_security(self, store: SecurityStore) -> None:
        """Test registering a new security."""
        from ditto_datahub.stores.security_store import SecurityRegistration

        registration = SecurityRegistration(
            src_code="600000.SH",
            symbol="600000",
            name="浦发银行",
            exchange="SSE",
            asset_class="stock",
            list_date="1999-11-10",
        )

        sid = store.register(1_000_001, registration)

        assert sid == 1_000_001

        # Verify security table
        row = store._client.fetchone("SELECT * FROM security WHERE sid = ?", [sid])
        assert row is not None
        assert row["symbol"] == "600000"
        assert row["name"] == "浦发银行"

        # Verify mapping table
        mapping = store._client.fetchone(
            """SELECT * FROM security_mapping
            WHERE sid = ? AND src_code = ?""",
            [sid, "600000.SH"],
        )
        assert mapping is not None
        assert mapping["source"] == "tushare"

    def test_resolve_sid_current(self, store: SecurityStore) -> None:
        """Test resolving src_code to sid (current)."""
        from ditto_datahub.stores.security_store import SecurityRegistration

        registration = SecurityRegistration(
            src_code="600000.SH",
            symbol="600000",
            name="浦发银行",
            exchange="SSE",
            asset_class="stock",
            list_date="1999-11-10",
        )

        store.register(1_000_001, registration)

        # Resolve current
        sid = store.resolve_sid("600000.SH", "tushare", asof=None)
        assert sid == 1_000_001

    def test_resolve_sid_pit(self, store: SecurityStore) -> None:
        """Test resolving src_code to sid with PIT."""
        from ditto_datahub.stores.security_store import SecurityRegistration

        # Register first security
        registration1 = SecurityRegistration(
            src_code="600000.SH",
            symbol="600000",
            name="浦发银行",
            exchange="SSE",
            asset_class="stock",
            list_date="1999-11-10",
        )
        store.register(1_000_001, registration1)

        # Simulate code change by updating effective_to
        store._client.execute(
            """UPDATE security_mapping
            SET effective_to = '2024-01-01'
            WHERE sid = ? AND src_code = ?""",
            [1_000_001, "600000.SH"],
        )
        store._client.commit()

        # Register new mapping for same SID
        store._client.execute(
            """INSERT INTO security_mapping
            (sid, source, src_code, effective_from, is_primary)
            VALUES (?, ?, ?, ?, TRUE)""",
            [1_000_001, "tushare", "600001.SH", "2024-01-01"],
        )
        store._client.commit()

        # Resolve with PIT date
        sid_before = store.resolve_sid("600000.SH", "tushare", asof="2023-12-31")
        assert sid_before == 1_000_001

        sid_after = store.resolve_sid("600001.SH", "tushare", asof="2024-01-02")
        assert sid_after == 1_000_001

    def test_resolve_sid_not_found(self, store: SecurityStore) -> None:
        """Test resolving non-existent src_code returns None."""
        sid = store.resolve_sid("INVALID.XYZ", "tushare", asof=None)
        assert sid is None

    def test_resolve_sids_batch(self, store: SecurityStore) -> None:
        """Test batch resolving src_codes to sids."""
        from ditto_datahub.stores.security_store import SecurityRegistration

        # Register multiple securities
        for i, src_code in enumerate(["600000.SH", "600001.SH", "600002.SH"]):
            registration = SecurityRegistration(
                src_code=src_code,
                symbol=f"60000{i}",
                name=f"测试{i}",
                exchange="SSE",
                asset_class="stock",
                list_date="1999-11-10",
            )
            store.register(1_000_001 + i, registration)

        # Batch resolve
        result = store.resolve_sids_batch(
            ["600000.SH", "600001.SH", "600002.SH", "INVALID.SH"],
            source="tushare",
        )

        assert len(result) == 3
        assert result["600000.SH"] == 1_000_001
        assert result["600001.SH"] == 1_000_002
        assert result["600002.SH"] == 1_000_003
        assert "INVALID.SH" not in result

    def test_resolve_by_symbol(self, store: SecurityStore) -> None:
        """Test resolving by symbol."""
        from ditto_datahub.stores.security_store import SecurityRegistration

        registration = SecurityRegistration(
            src_code="600000.SH",
            symbol="600000",
            name="浦发银行",
            exchange="SSE",
            asset_class="stock",
            list_date="1999-11-10",
        )
        store.register(1_000_001, registration)

        sids = store.resolve_by_symbol("600000", "tushare")
        assert len(sids) == 1
        assert sids[0] == 1_000_001

    def test_get_src_code(self, store: SecurityStore) -> None:
        """Test reverse lookup: sid to src_code."""
        from ditto_datahub.stores.security_store import SecurityRegistration

        registration = SecurityRegistration(
            src_code="600000.SH",
            symbol="600000",
            name="浦发银行",
            exchange="SSE",
            asset_class="stock",
            list_date="1999-11-10",
        )
        store.register(1_000_001, registration)

        src_code = store.get_src_code(1_000_001, "tushare")
        assert src_code == "600000.SH"

    def test_get_by_sid(self, store: SecurityStore) -> None:
        """Test getting security by sid."""
        from ditto_datahub.stores.security_store import SecurityRegistration

        registration = SecurityRegistration(
            src_code="600000.SH",
            symbol="600000",
            name="浦发银行",
            exchange="SSE",
            asset_class="stock",
            list_date="1999-11-10",
        )
        store.register(1_000_001, registration)

        row = store.get_by_sid(1_000_001)
        assert row is not None
        assert row["sid"] == 1_000_001
        assert row["symbol"] == "600000"
        assert row["name"] == "浦发银行"
        assert row["asset_class"] == "stock"

    def test_find_securities(self, store: SecurityStore) -> None:
        """Test finding securities with filters."""
        from ditto_datahub.stores.security_store import SecurityRegistration

        # Register multiple securities
        registration1 = SecurityRegistration(
            src_code="600000.SH",
            symbol="600000",
            name="浦发银行",
            exchange="SSE",
            asset_class="stock",
            list_date="1999-11-10",
        )
        store.register(1_000_001, registration1)

        registration2 = SecurityRegistration(
            src_code="510300.SH",
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

    def test_list_sids(self, store: SecurityStore) -> None:
        """Test listing sids with filters."""
        from ditto_datahub.stores.security_store import SecurityRegistration

        registration1 = SecurityRegistration(
            src_code="600000.SH",
            symbol="600000",
            name="浦发银行",
            exchange="SSE",
            asset_class="stock",
            list_date="1999-11-10",
        )
        store.register(1_000_001, registration1)

        registration2 = SecurityRegistration(
            src_code="510300.SH",
            symbol="510300",
            name="沪深300ETF",
            exchange="SSE",
            asset_class="etf",
            list_date="2012-05-28",
        )
        store.register(2_000_001, registration2)

        # List all sids
        all_sids = store.list_sids()
        assert len(all_sids) == 2

        # List only stocks
        stock_sids = store.list_sids(asset_class="stock")
        assert len(stock_sids) == 1
        assert stock_sids[0] == 1_000_001

    def test_get_symbol(self, store: SecurityStore) -> None:
        """Test getting symbol by sid."""
        from ditto_datahub.stores.security_store import SecurityRegistration

        registration = SecurityRegistration(
            src_code="600000.SH",
            symbol="600000",
            name="浦发银行",
            exchange="SSE",
            asset_class="stock",
            list_date="1999-11-10",
        )
        store.register(1_000_001, registration)

        symbol = store.get_symbol(1_000_001)
        assert symbol == "600000"

    def test_get_sid_symbol_map(self, store: SecurityStore) -> None:
        """Test getting sid to symbol mapping."""
        from ditto_datahub.stores.security_store import SecurityRegistration

        registration1 = SecurityRegistration(
            src_code="600000.SH",
            symbol="600000",
            name="浦发银行",
            exchange="SSE",
            asset_class="stock",
            list_date="1999-11-10",
        )
        store.register(1_000_001, registration1)

        registration2 = SecurityRegistration(
            src_code="600001.SH",
            symbol="600001",
            name="邯郸钢铁",
            exchange="SSE",
            asset_class="stock",
            list_date="1998-12-31",
        )
        store.register(1_000_002, registration2)

        # Get all mapping
        mapping = store.get_sid_symbol_map()
        assert len(mapping) == 2
        assert mapping[1_000_001] == "600000"
        assert mapping[1_000_002] == "600001"

        # Get specific sids
        partial_mapping = store.get_sid_symbol_map([1_000_001])
        assert len(partial_mapping) == 1
        assert partial_mapping[1_000_001] == "600000"

    def test_enrich_with_symbol(self, store: SecurityStore) -> None:
        """Test enriching DataFrame with symbol column."""
        from ditto_datahub.stores.security_store import SecurityRegistration

        registration = SecurityRegistration(
            src_code="600000.SH",
            symbol="600000",
            name="浦发银行",
            exchange="SSE",
            asset_class="stock",
            list_date="1999-11-10",
        )
        store.register(1_000_001, registration)

        # Create test DataFrame
        df = pl.DataFrame({"sid": [1_000_001], "value": [100]})

        # Enrich with symbol
        enriched = store.enrich_with_symbol(df)

        assert "symbol" in enriched.columns
        assert enriched["symbol"][0] == "600000"
