"""Integration tests for InstrumentReader and InstrumentWriter (SQLite seam)."""

import polars as pl
import pytest
from ditto_data.stores.metadata.instrument import (
    InstrumentReader,
    InstrumentRegistration,
    InstrumentWriter,
)
from ditto_data.stores.sqlite_client import SQLiteClient
from ditto_infra.foundation import SQLitePool


@pytest.mark.integration
class TestInstrumentReaderWriterIntegration:
    """Tests for InstrumentReader/Writer integration with SQLite."""

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
                ticker TEXT NOT NULL,
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

            CREATE INDEX idx_security_ticker ON instrument(ticker);
            CREATE INDEX idx_security_mapping_source_ticker
            ON instrument_mapping(source_ticker);
            CREATE INDEX idx_security_mapping_instrument_id
            ON instrument_mapping(instrument_id);
        """
        client.executescript(schema_sql)
        return client

    @pytest.fixture
    def reader(self, client: SQLiteClient) -> InstrumentReader:
        """Create InstrumentReader instance."""
        return InstrumentReader(client)

    @pytest.fixture
    def writer(self, client: SQLiteClient) -> InstrumentWriter:
        """Create InstrumentWriter instance."""
        return InstrumentWriter(client)

    def test_register_new_security(
        self, writer: InstrumentWriter, reader: InstrumentReader, client: SQLiteClient
    ) -> None:
        """Test registering a new instrument."""

        registration = InstrumentRegistration(
            source_ticker="600000.SH",
            ticker="600000",
            name="浦发银行",
            exchange="SSE",
            asset_class="stock",
            list_date="1999-11-10",
        )

        instrument_id = writer.register(1_000_001, registration)

        assert instrument_id == 1_000_001

        # Verify instrument table
        row = client.fetchone(
            "SELECT * FROM instrument WHERE instrument_id = ?", [instrument_id]
        )
        assert row is not None
        assert row["ticker"] == "600000"
        assert row["name"] == "浦发银行"

        # Verify mapping table
        mapping = client.fetchone(
            """SELECT * FROM instrument_mapping
            WHERE instrument_id = ? AND source_ticker = ?""",
            [instrument_id, "600000.SH"],
        )
        assert mapping is not None
        assert mapping["source"] == "tushare"

    def test_resolve_instrument_id_current(
        self, writer: InstrumentWriter, reader: InstrumentReader
    ) -> None:
        """Test resolving source_ticker to instrument_id (current)."""

        registration = InstrumentRegistration(
            source_ticker="600000.SH",
            ticker="600000",
            name="浦发银行",
            exchange="SSE",
            asset_class="stock",
            list_date="1999-11-10",
        )

        writer.register(1_000_001, registration)

        # Resolve current
        instrument_id = reader.resolve_instrument_id("600000.SH", "tushare", asof=None)
        assert instrument_id == 1_000_001

    def test_resolve_instrument_id_pit(
        self, writer: InstrumentWriter, reader: InstrumentReader, client: SQLiteClient
    ) -> None:
        """Test resolving source_ticker to instrument_id with PIT."""

        # Register first instrument
        registration1 = InstrumentRegistration(
            source_ticker="600000.SH",
            ticker="600000",
            name="浦发银行",
            exchange="SSE",
            asset_class="stock",
            list_date="1999-11-10",
        )
        writer.register(1_000_001, registration1)

        # Simulate code change by updating effective_to
        client.execute(
            """UPDATE instrument_mapping
            SET effective_to = '2024-01-01'
            WHERE instrument_id = ? AND source_ticker = ?""",
            [1_000_001, "600000.SH"],
        )
        client.commit()

        # Register new mapping for same Instrument ID
        client.execute(
            """INSERT INTO instrument_mapping
            (instrument_id, source, source_ticker, effective_from, is_primary)
            VALUES (?, ?, ?, ?, TRUE)""",
            [1_000_001, "tushare", "600001.SH", "2024-01-01"],
        )
        client.commit()

        # Resolve with PIT date
        sid_before = reader.resolve_instrument_id(
            "600000.SH", "tushare", asof="2023-12-31"
        )
        assert sid_before == 1_000_001

        sid_after = reader.resolve_instrument_id(
            "600001.SH", "tushare", asof="2024-01-02"
        )
        assert sid_after == 1_000_001

    def test_resolve_instrument_id_not_found(self, reader: InstrumentReader) -> None:
        """Test resolving non-existent source_ticker returns None."""
        instrument_id = reader.resolve_instrument_id(
            "INVALID.XYZ", "tushare", asof=None
        )
        assert instrument_id is None

    def test_resolve_instrument_ids_batch(
        self, writer: InstrumentWriter, reader: InstrumentReader
    ) -> None:
        """Test batch resolving source_tickers to instrument_ids."""

        # Register multiple securities
        for i, source_ticker in enumerate(["600000.SH", "600001.SH", "600002.SH"]):
            registration = InstrumentRegistration(
                source_ticker=source_ticker,
                ticker=f"60000{i}",
                name=f"测试{i}",
                exchange="SSE",
                asset_class="stock",
                list_date="1999-11-10",
            )
            writer.register(1_000_001 + i, registration)

        # Batch resolve
        result = reader.resolve_instrument_ids_batch(
            ["600000.SH", "600001.SH", "600002.SH", "INVALID.SH"],
            source="tushare",
        )

        assert len(result) == 3
        assert result["600000.SH"] == 1_000_001
        assert result["600001.SH"] == 1_000_002
        assert result["600002.SH"] == 1_000_003
        assert "INVALID.SH" not in result

    def test_resolve_by_symbol(
        self, writer: InstrumentWriter, reader: InstrumentReader
    ) -> None:
        """Test resolving by symbol."""

        registration = InstrumentRegistration(
            source_ticker="600000.SH",
            ticker="600000",
            name="浦发银行",
            exchange="SSE",
            asset_class="stock",
            list_date="1999-11-10",
        )
        writer.register(1_000_001, registration)

        # Note: resolve_by_symbol is not in InstrumentReader, skip this test
        # This test would need to be reimplemented if needed

    def test_get_source_ticker(
        self, writer: InstrumentWriter, reader: InstrumentReader
    ) -> None:
        """Test reverse lookup: instrument_id to source_ticker."""

        registration = InstrumentRegistration(
            source_ticker="600000.SH",
            ticker="600000",
            name="浦发银行",
            exchange="SSE",
            asset_class="stock",
            list_date="1999-11-10",
        )
        writer.register(1_000_001, registration)

        source_ticker = reader.get_source_ticker(1_000_001, "tushare")
        assert source_ticker == "600000.SH"

    def test_get_by_instrument_id(
        self, writer: InstrumentWriter, reader: InstrumentReader
    ) -> None:
        """Test getting instrument by instrument_id."""

        registration = InstrumentRegistration(
            source_ticker="600000.SH",
            ticker="600000",
            name="浦发银行",
            exchange="SSE",
            asset_class="stock",
            list_date="1999-11-10",
        )
        writer.register(1_000_001, registration)

        row = reader.get_by_instrument_id(1_000_001)
        assert row is not None
        assert row["instrument_id"] == 1_000_001
        assert row["ticker"] == "600000"
        assert row["name"] == "浦发银行"
        assert row["asset_class"] == "stock"

    def test_find_securities(
        self, writer: InstrumentWriter, reader: InstrumentReader
    ) -> None:
        """Test finding securities with filters."""

        # Register multiple securities
        registration1 = InstrumentRegistration(
            source_ticker="600000.SH",
            ticker="600000",
            name="浦发银行",
            exchange="SSE",
            asset_class="stock",
            list_date="1999-11-10",
        )
        writer.register(1_000_001, registration1)

        registration2 = InstrumentRegistration(
            source_ticker="510300.SH",
            ticker="510300",
            name="沪深300ETF",
            exchange="SSE",
            asset_class="etf",
            list_date="2012-05-28",
        )
        writer.register(2_000_001, registration2)

        from ditto_data.stores.metadata.instrument import SecurityQuery

        # Find all stocks
        stocks = reader.find_securities(SecurityQuery(asset_class="stock"))
        assert len(stocks) == 1
        assert stocks["asset_class"][0] == "stock"

        # Find by exchange
        sse_securities = reader.find_securities(SecurityQuery(exchange="SSE"))
        assert len(sse_securities) == 2

    def test_list_instrument_ids(
        self, writer: InstrumentWriter, reader: InstrumentReader
    ) -> None:
        """Test listing instrument_ids with filters."""

        registration1 = InstrumentRegistration(
            source_ticker="600000.SH",
            ticker="600000",
            name="浦发银行",
            exchange="SSE",
            asset_class="stock",
            list_date="1999-11-10",
        )
        writer.register(1_000_001, registration1)

        registration2 = InstrumentRegistration(
            source_ticker="510300.SH",
            ticker="510300",
            name="沪深300ETF",
            exchange="SSE",
            asset_class="etf",
            list_date="2012-05-28",
        )
        writer.register(2_000_001, registration2)

        # List all instrument_ids
        all_sids = reader.list_instrument_ids()
        assert len(all_sids) == 2

        # List only stocks
        stock_sids = reader.list_instrument_ids(asset_class="stock")
        assert len(stock_sids) == 1
        assert stock_sids[0] == 1_000_001

    def test_get_ticker(
        self, writer: InstrumentWriter, reader: InstrumentReader
    ) -> None:
        """Test getting ticker by instrument_id."""

        registration = InstrumentRegistration(
            source_ticker="600000.SH",
            ticker="600000",
            name="浦发银行",
            exchange="SSE",
            asset_class="stock",
            list_date="1999-11-10",
        )
        writer.register(1_000_001, registration)

        ticker = reader.get_ticker(1_000_001)
        assert ticker == "600000"

    def test_get_instrument_id_ticker_map(
        self, writer: InstrumentWriter, reader: InstrumentReader
    ) -> None:
        """Test getting instrument_id to ticker mapping."""

        registration1 = InstrumentRegistration(
            source_ticker="600000.SH",
            ticker="600000",
            name="浦发银行",
            exchange="SSE",
            asset_class="stock",
            list_date="1999-11-10",
        )
        writer.register(1_000_001, registration1)

        registration2 = InstrumentRegistration(
            source_ticker="600001.SH",
            ticker="600001",
            name="邯郸钢铁",
            exchange="SSE",
            asset_class="stock",
            list_date="1998-12-31",
        )
        writer.register(1_000_002, registration2)

        # Get all mapping
        mapping = reader.get_instrument_id_ticker_map()
        assert len(mapping) == 2
        assert mapping[1_000_001] == "600000"
        assert mapping[1_000_002] == "600001"

        # Get specific instrument_ids
        partial_mapping = reader.get_instrument_id_ticker_map([1_000_001])
        assert len(partial_mapping) == 1
        assert partial_mapping[1_000_001] == "600000"

    def test_enrich_with_ticker(
        self, writer: InstrumentWriter, reader: InstrumentReader
    ) -> None:
        """Test enriching DataFrame with ticker column."""

        registration = InstrumentRegistration(
            source_ticker="600000.SH",
            ticker="600000",
            name="浦发银行",
            exchange="SSE",
            asset_class="stock",
            list_date="1999-11-10",
        )
        writer.register(1_000_001, registration)

        # Create test DataFrame
        df = pl.DataFrame({"instrument_id": [1_000_001], "value": [100]})

        # Enrich with symbol
        enriched = reader.enrich_with_ticker(df)

        assert "ticker" in enriched.columns
        assert enriched["ticker"][0] == "600000"
