"""Tests for InstrumentReader and InstrumentWriter (CQRS pattern)."""

import polars as pl
import pytest
from ditto_data.storage.metadata.instrument import (
    ETFExtension,
    IndexExtension,
    InstrumentReader,
    InstrumentRegistration,
    InstrumentWriter,
    SecurityQuery,
    StockExtension,
)
from ditto_data.storage.metadata.instrument.instrument_reader import _build_in_clause
from ditto_platform.foundation import DataCache, SQLiteClient
from pytest_mock import MockerFixture


@pytest.mark.integration
class TestInstrumentReader:
    """
    Tests for InstrumentReader.

    PIT (Pipeline Integration Tests) - tests complete data ingestion flow.
    These tests require more resources and time than unit tests.
    """

    @pytest.fixture(autouse=True)
    def setup(self, sqlite_client: SQLiteClient) -> None:
        """使用 fixture 自动注入已初始化的数据库客户端."""
        self.client = sqlite_client
        self.reader = InstrumentReader(self.client)

    def test_resolve_instrument_id_current_mapping(self) -> None:
        """Test resolving instrument_id for current mapping."""
        # Insert test data
        self.client.execute("""
            INSERT INTO instrument (
                instrument_id, ticker, name, exchange, asset_class, list_date
            )
            VALUES (100000001, '600000', '浦发银行', 'SSE', 'stock', '1999-11-10')
        """)
        self.client.execute("""
            INSERT INTO instrument_mapping
            (instrument_id, source, source_ticker, effective_from)
            VALUES (100000001, 'tushare', '600000.SH', '1999-11-10')
        """)
        self.client.commit()

        # Test resolve
        instrument_id = self.reader.resolve_instrument_id(
            "600000.SH", "tushare", asof=None
        )
        assert instrument_id == 100000001

    def test_resolve_instrument_id_with_pit(self) -> None:
        """Test resolving instrument_id with PIT (asof parameter)."""
        # Insert test data with historical mapping
        self.client.execute("""
            INSERT INTO instrument (
                instrument_id, ticker, name, exchange, asset_class, list_date
            )
            VALUES (100000001, '000022', '深赤湾A', 'SZSE', 'stock', '1990-01-01')
        """)
        # Mapping valid until 2018-12-25
        self.client.execute("""
            INSERT INTO instrument_mapping
            (instrument_id, source, source_ticker, effective_from, effective_to)
            VALUES (100000001, 'tushare', '000022.SZ', '1990-01-01', '2018-12-25')
        """)
        self.client.commit()

        # Query before expiration
        instrument_id = self.reader.resolve_instrument_id(
            "000022.SZ", "tushare", asof="2017-01-01"
        )
        assert instrument_id == 100000001

        # Query after expiration - should return None
        instrument_id = self.reader.resolve_instrument_id(
            "000022.SZ", "tushare", asof="2019-01-01"
        )
        assert instrument_id is None

    def test_resolve_instrument_id_cached(self) -> None:
        """Test that resolve_instrument_id uses DataCache for current queries."""
        # Create reader with DataCache
        data_cache = DataCache(ttl_seconds=300, max_size=1000, enable_metrics=False)
        reader_with_cache = InstrumentReader(self.client, cache=data_cache)

        self.client.execute("""
            INSERT INTO instrument (
                instrument_id, ticker, name, exchange, asset_class, list_date
            )
            VALUES (100000001, '600000', 'Test', 'SSE', 'stock', '1999-11-10')
        """)
        self.client.execute("""
            INSERT INTO instrument_mapping
            (instrument_id, source, source_ticker, effective_from)
            VALUES (100000001, 'tushare', '600000.SH', '1999-11-10')
        """)
        self.client.commit()

        # First call - cache miss
        sid1 = reader_with_cache.resolve_instrument_id(
            "600000.SH", "tushare", asof=None
        )
        assert sid1 == 100000001

        # Second call - cache hit
        sid2 = reader_with_cache.resolve_instrument_id(
            "600000.SH", "tushare", asof=None
        )
        assert sid2 == 100000001

        # PIT 查询也应该被缓存
        sid3 = reader_with_cache.resolve_instrument_id(
            "600000.SH", "tushare", asof="2020-01-01"
        )
        assert sid3 == 100000001

    def test_resolve_instrument_id_uses_empty_cache_from_first_lookup(self) -> None:
        """The first lookup should populate an empty configured DataCache."""
        data_cache = DataCache(ttl_seconds=300, max_size=1000, enable_metrics=False)
        reader_with_cache = InstrumentReader(self.client, cache=data_cache)
        self.client.execute("""
            INSERT INTO instrument (
                instrument_id, ticker, name, exchange, asset_class, list_date
            )
            VALUES (100000001, '600000', 'Test', 'SSE', 'stock', '1999-11-10')
        """)
        self.client.execute("""
            INSERT INTO instrument_mapping
            (instrument_id, source, source_ticker, effective_from)
            VALUES (100000001, 'tushare', '600000.SH', '1999-11-10')
        """)
        self.client.commit()

        sid = reader_with_cache.resolve_instrument_id("600000.SH", "tushare")

        assert sid == 100000001
        assert "instrument_id:600000.SH:tushare:current" in data_cache

        self.client.execute(
            "UPDATE instrument_mapping SET effective_to = '2020-01-01'"
            " WHERE source = 'tushare' AND source_ticker = '600000.SH'"
        )
        self.client.commit()

        assert reader_with_cache.resolve_instrument_id("600000.SH", "tushare") == sid

    def test_resolve_instrument_id_caches_negative_lookup(self) -> None:
        """Missing instrument lookups should cache as None until invalidated."""
        data_cache = DataCache(ttl_seconds=300, max_size=1000, enable_metrics=False)
        reader_with_cache = InstrumentReader(self.client, cache=data_cache)

        assert reader_with_cache.resolve_instrument_id("600999.SH", "tushare") is None
        assert "instrument_id:600999.SH:tushare:current" in data_cache

        self.client.execute("""
            INSERT INTO instrument (
                instrument_id, ticker, name, exchange, asset_class, list_date
            )
            VALUES (100999001, '600999', 'Late Insert', 'SSE', 'stock', '2020-01-01')
        """)
        self.client.execute("""
            INSERT INTO instrument_mapping
            (instrument_id, source, source_ticker, effective_from)
            VALUES (100999001, 'tushare', '600999.SH', '2020-01-01')
        """)
        self.client.commit()

        assert reader_with_cache.resolve_instrument_id("600999.SH", "tushare") is None

    def test_resolve_instrument_ids_batch(self) -> None:
        """Test batch resolution of source_tickers to instrument_ids."""
        # Insert test data
        for i, code in enumerate(["600000.SH", "600001.SH", "600002.SH"]):
            instrument_id = 100000001 + i
            sql = (
                "INSERT INTO instrument "
                "(instrument_id, ticker, name, exchange, asset_class, list_date) "
                f"VALUES ({instrument_id}, '60000{i}', 'Stock{i}', "
                "'SSE', 'stock', '2000-01-01')"
            )
            self.client.execute(sql)

            sql = (
                "INSERT INTO instrument_mapping "
                "(instrument_id, source, source_ticker, effective_from) "
                f"VALUES ({instrument_id}, 'tushare', '{code}', '2000-01-01')"
            )
            self.client.execute(sql)

        self.client.commit()

        # Test batch resolve
        result = self.reader.resolve_instrument_ids_batch(
            ["600000.SH", "600001.SH", "600003.SH"],  # 600003 doesn't exist
            source="tushare",
            asof=None,
        )

        assert result["600000.SH"] == 100000001
        assert result["600001.SH"] == 100000002
        assert "600003.SH" not in result  # Not found

    def test_get_by_instrument_id(self) -> None:
        """Test getting instrument by instrument_id."""
        sql = (
            "INSERT INTO instrument "
            "(instrument_id, ticker, name, exchange, "
            "asset_class, list_date, is_active) "
            "VALUES (100000001, '600000', 'Test Bank', 'SSE', 'stock', "
            "'1999-11-10', TRUE)"
        )
        self.client.execute(sql)
        self.client.commit()

        result = self.reader.get_by_instrument_id(100000001)
        assert result is not None
        assert result["instrument_id"] == 100000001
        assert result["ticker"] == "600000"
        assert result["name"] == "Test Bank"

    def test_get_by_instrument_id_not_found(self) -> None:
        """Test getting non-existent instrument_id returns None."""
        result = self.reader.get_by_instrument_id(999999999)
        assert result is None

    def test_get_source_ticker(self) -> None:
        """Test reverse lookup: instrument_id to source_ticker."""
        self.client.execute("""
            INSERT INTO instrument (
                instrument_id, ticker, name, exchange, asset_class, list_date
            )
            VALUES (100000001, '600000', 'Test', 'SSE', 'stock', '1999-11-10')
        """)
        self.client.execute("""
            INSERT INTO instrument_mapping
            (instrument_id, source, source_ticker, effective_from)
            VALUES (100000001, 'tushare', '600000.SH', '1999-11-10')
        """)
        self.client.commit()

        source_ticker = self.reader.get_source_ticker(100000001, "tushare", asof=None)
        assert source_ticker == "600000.SH"

    def test_get_source_ticker_with_pit_window(self) -> None:
        """Reverse lookup respects historical mapping windows."""
        self.client.execute("""
            INSERT INTO instrument (
                instrument_id, ticker, name, exchange, asset_class, list_date
            )
            VALUES (100000001, '000022', 'Old Code', 'SZSE', 'stock', '1990-01-01')
        """)
        self.client.execute("""
            INSERT INTO instrument_mapping
            (instrument_id, source, source_ticker, effective_from, effective_to)
            VALUES (100000001, 'tushare', '000022.SZ', '1990-01-01', '2018-12-25')
        """)
        self.client.execute("""
            INSERT INTO instrument_mapping
            (instrument_id, source, source_ticker, effective_from)
            VALUES (100000001, 'tushare', '001872.SZ', '2018-12-25')
        """)
        self.client.commit()

        assert (
            self.reader.get_source_ticker(100000001, "tushare", asof="2018-12-24")
            == "000022.SZ"
        )
        assert (
            self.reader.get_source_ticker(100000001, "tushare", asof="2018-12-25")
            == "001872.SZ"
        )

    def test_list_instrument_ids(self) -> None:
        """Test listing all instrument_ids with filters."""
        # Insert test data
        for i in range(3):
            instrument_id = 100000001 + i
            exchange = "SSE" if i < 2 else "SZSE"
            sql = (
                "INSERT INTO instrument "
                "(instrument_id, ticker, name, exchange, "
                "asset_class, list_date, is_active) "
                f"VALUES ({instrument_id}, '60{i:04d}', 'Stock{i}', '{exchange}', "
                "'stock', "
                "'2000-01-01', TRUE)"
            )
            self.client.execute(sql)

        self.client.commit()

        # List all
        all_sids = self.reader.list_instrument_ids()
        assert len(all_sids) == 3

        # Filter by exchange
        sse_sids = self.reader.list_instrument_ids(exchange="SSE")
        assert len(sse_sids) == 2
        assert 100000001 in sse_sids
        assert 100000002 in sse_sids

        # Filter by asset class
        stock_sids = self.reader.list_instrument_ids(asset_class="stock")
        assert len(stock_sids) == 3

    def test_list_instrument_ids_with_is_active_none(self) -> None:
        """Test listing with is_active=None returns active and inactive rows."""
        # Insert test data: 2 active, 1 inactive
        for i in range(3):
            instrument_id = 100000001 + i
            is_active = "TRUE" if i < 2 else "FALSE"
            sql = (
                "INSERT INTO instrument "
                "(instrument_id, ticker, name, exchange, "
                "asset_class, list_date, is_active) "
                f"VALUES ({instrument_id}, '60{i:04d}', 'Stock{i}', 'SSE', 'stock', "
                f"'2000-01-01', {is_active})"
            )
            self.client.execute(sql)

        self.client.commit()

        # Default (is_active=True) should return only active
        active_sids = self.reader.list_instrument_ids()
        assert len(active_sids) == 2
        assert 100000001 in active_sids
        assert 100000002 in active_sids
        assert 100000003 not in active_sids

        # is_active=False should return only inactive
        inactive_sids = self.reader.list_instrument_ids(is_active=False)
        assert len(inactive_sids) == 1
        assert 100000003 in inactive_sids

        # is_active=None should return ALL (both active and inactive)
        all_sids = self.reader.list_instrument_ids(is_active=None)
        assert len(all_sids) == 3
        assert 100000001 in all_sids
        assert 100000002 in all_sids
        assert 100000003 in all_sids

    def test_get_ticker(self) -> None:
        """Test getting symbol by instrument_id."""
        self.client.execute("""
            INSERT INTO instrument (
                instrument_id, ticker, name, exchange, asset_class, list_date
            )
            VALUES (100000001, '600000', 'Test', 'SSE', 'stock', '1999-11-10')
        """)
        self.client.commit()

        symbol = self.reader.get_ticker(100000001)
        assert symbol == "600000"

    def test_get_instrument_id_ticker_map(self) -> None:
        """Test getting batch instrument_id to symbol mapping."""
        # Insert test data
        for i in range(3):
            instrument_id = 100000001 + i
            sql = (
                "INSERT INTO instrument "
                "(instrument_id, ticker, name, exchange, "
                "asset_class, list_date, is_active) "
                f"VALUES ({instrument_id}, '60{i:04d}', 'Stock{i}', 'SSE', 'stock', "
                "'2000-01-01', TRUE)"
            )
            self.client.execute(sql)

        self.client.commit()

        mapping = self.reader.get_instrument_id_ticker_map()
        assert len(mapping) == 3
        assert mapping[100000001] == "600000"
        assert mapping[100000002] == "600001"

    def test_get_instrument_id_ticker_map_uses_empty_cache_from_first_lookup(
        self,
    ) -> None:
        """Explicit ticker map queries should populate an empty configured DataCache."""
        data_cache = DataCache(ttl_seconds=300, max_size=1000, enable_metrics=False)
        reader_with_cache = InstrumentReader(self.client, cache=data_cache)
        self.client.execute("""
            INSERT INTO instrument (
                instrument_id, ticker, name, exchange, asset_class, list_date, is_active
            )
            VALUES (100000001, '600000', 'Test', 'SSE', 'stock', '1999-11-10', TRUE)
        """)
        self.client.commit()

        mapping = reader_with_cache.get_instrument_id_ticker_map([100000001])

        assert mapping == {100000001: "600000"}
        assert "instrument_id_ticker_map:100000001" in data_cache

        self.client.execute(
            "UPDATE instrument SET ticker = '600001' WHERE instrument_id = 100000001"
        )
        self.client.commit()

        assert reader_with_cache.get_instrument_id_ticker_map([100000001]) == mapping

    def test_enrich_with_ticker(self) -> None:
        """Test enriching DataFrame with symbol column."""
        # Insert test data
        self.client.execute("""
            INSERT INTO instrument (
                instrument_id, ticker, name, exchange, asset_class, list_date
            )
            VALUES (100000001, '600000', 'Test', 'SSE', 'stock', '1999-11-10')
        """)
        self.client.commit()

        # Create test DataFrame
        df = pl.DataFrame(
            {
                "instrument_id": [100000001, 100000001],
                "close": [10.5, 11.0],
            }
        )

        # Enrich
        result = self.reader.enrich_with_ticker(df)

        assert "ticker" in result.columns
        assert result["ticker"].to_list() == ["600000", "600000"]

    def test_enrich_with_ticker_empty_df(self) -> None:
        """Test enriching empty DataFrame returns empty."""
        df = pl.DataFrame(schema={"instrument_id": pl.Int64, "close": pl.Float64})
        result = self.reader.enrich_with_ticker(df)
        assert result.is_empty()

    def test_find_securities(self) -> None:
        """Test finding securities with various filters."""
        # Insert test data
        self.client.execute("""
            INSERT INTO instrument
            (instrument_id, ticker, name, exchange, asset_class, list_date, is_active)
            VALUES (100000001, '600000', 'Bank', 'SSE', 'stock', '1999-11-10', TRUE)
        """)
        self.client.execute("""
            INSERT INTO instrument_mapping
            (instrument_id, source, source_ticker, effective_from)
            VALUES (100000001, 'tushare', '600000.SH', '1999-11-10')
        """)
        self.client.commit()

        # Find by source_ticker
        result = self.reader.find_securities(
            SecurityQuery(source_tickers=["600000.SH"], source="tushare"),
        )
        assert len(result) == 1
        assert result["instrument_id"][0] == 100000001

        # Find by asset_class
        result = self.reader.find_securities(SecurityQuery(asset_class="stock"))
        assert len(result) == 1

        # Find by exchange
        result = self.reader.find_securities(SecurityQuery(exchange="SSE"))
        assert len(result) == 1

    def test_resolve_instrument_ids_batch_empty_input(self) -> None:
        """Batch resolution should short-circuit empty requests."""
        assert self.reader.resolve_instrument_ids_batch([], source="tushare") == {}

    def test_resolve_instrument_ids_batch_with_pit_window(self) -> None:
        """Batch resolution applies PIT mapping windows."""
        self.client.execute("""
            INSERT INTO instrument (
                instrument_id, ticker, name, exchange, asset_class, list_date
            )
            VALUES (100000001, '000022', 'Old Code', 'SZSE', 'stock', '1990-01-01')
        """)
        self.client.execute("""
            INSERT INTO instrument_mapping
            (instrument_id, source, source_ticker, effective_from, effective_to)
            VALUES (100000001, 'tushare', '000022.SZ', '1990-01-01', '2018-12-25')
        """)
        self.client.execute("""
            INSERT INTO instrument_mapping
            (instrument_id, source, source_ticker, effective_from)
            VALUES (100000001, 'tushare', '001872.SZ', '2018-12-25')
        """)
        self.client.commit()

        result = self.reader.resolve_instrument_ids_batch(
            ["000022.SZ", "001872.SZ"],
            source="tushare",
            asof="2018-12-24",
        )

        assert result == {"000022.SZ": 100000001}

    def test_find_securities_returns_empty_dataframe_for_no_rows(self) -> None:
        """No matching securities should return an empty Polars DataFrame."""
        result = self.reader.find_securities(
            SecurityQuery(source_tickers=["missing"], is_active=None)
        )

        assert result.is_empty()

    def test_find_securities_with_pit_and_min_list_days(self) -> None:
        """Security query applies source PIT and minimum listing age together."""
        for instrument_id, ticker, source_ticker, list_date in [
            (100000001, "600000", "600000.SH", "1999-11-10"),
            (100000002, "600001", "600001.SH", "2024-01-15"),
        ]:
            self.client.execute(
                """INSERT INTO instrument (
                    instrument_id, ticker, name, exchange, asset_class, list_date
                )
                VALUES (?, ?, ?, 'SSE', 'stock', ?)""",
                [instrument_id, ticker, ticker, list_date],
            )
            self.client.execute(
                """INSERT INTO instrument_mapping
                (instrument_id, source, source_ticker, effective_from)
                VALUES (?, 'tushare', ?, ?)""",
                [instrument_id, source_ticker, list_date],
            )
        self.client.commit()

        result = self.reader.find_securities(
            SecurityQuery(
                source_tickers=["600000.SH", "600001.SH"],
                source="tushare",
                asof="2024-01-20",
                min_list_days=30,
                is_active=None,
            )
        )

        assert result["instrument_id"].to_list() == [100000001]

    def test_get_with_extension_merges_known_extension(self) -> None:
        """Full instrument lookup merges extension fields for known asset classes."""
        writer = InstrumentWriter(self.client)
        writer.register(
            100000001,
            InstrumentRegistration(
                source_ticker="600000.SH",
                ticker="600000",
                name="Test Bank",
                exchange="SSE",
                asset_class="stock",
                list_date="1999-11-10",
                extension=StockExtension(
                    instrument_id=100000001,
                    list_status="L",
                    industry_id=801010,
                ),
            ),
        )

        result = self.reader.get_with_extension(100000001)

        assert result is not None
        assert result["instrument_id"] == 100000001
        assert result["list_status"] == "L"
        assert result["industry_id"] == 801010

    def test_get_with_extension_merges_etf_and_index_extensions(self) -> None:
        """Full instrument lookup also merges ETF and index extension fields."""
        writer = InstrumentWriter(self.client)
        writer.register(
            200000001,
            InstrumentRegistration(
                source_ticker="510300.SH",
                ticker="510300",
                name="ETF",
                exchange="SSE",
                asset_class="etf",
                list_date="2012-05-28",
                extension=ETFExtension(
                    instrument_id=200000001,
                    fund_type="equity",
                    fund_manager="Manager",
                    establish_date="2012-05-28",
                    tracking_index="000300.SH",
                ),
            ),
        )
        writer.register(
            300000001,
            InstrumentRegistration(
                source_ticker="000300.SH",
                ticker="000300",
                name="Index",
                exchange="SSE",
                asset_class="index",
                list_date="2005-04-08",
                extension=IndexExtension(
                    instrument_id=300000001,
                    base_date="2004-12-31",
                    base_point=1000.0,
                    num_constituents=300,
                ),
            ),
        )

        etf = self.reader.get_with_extension(200000001)
        index = self.reader.get_with_extension(300000001)

        assert etf is not None
        assert etf["fund_type"] == "equity"
        assert etf["tracking_index"] == "000300.SH"
        assert index is not None
        assert index["base_point"] == 1000.0
        assert index["num_constituents"] == 300

    def test_get_with_extension_handles_missing_or_unknown_extension(self) -> None:
        """Full instrument lookup remains useful without a matching extension row."""
        self.client.execute("""
            INSERT INTO instrument (
                instrument_id, ticker, name, exchange, asset_class, list_date
            )
            VALUES (900000001, 'X001', 'Unknown', 'SSE', 'commodity', '2020-01-01')
        """)
        self.client.execute("""
            INSERT INTO instrument (
                instrument_id, ticker, name, exchange, asset_class, list_date
            )
            VALUES (100000001, '600000', 'No Extension', 'SSE', 'stock', '1999-11-10')
        """)
        self.client.commit()

        assert self.reader.get_with_extension(999999999) is None
        unknown = self.reader.get_with_extension(900000001)
        stock_without_extension = self.reader.get_with_extension(100000001)

        assert unknown is not None
        assert unknown["asset_class"] == "commodity"
        assert stock_without_extension is not None
        assert "list_status" not in stock_without_extension

    def test_find_securities_with_extensions_for_supported_asset_classes(
        self,
    ) -> None:
        """Extension query joins the requested extension table."""
        writer = InstrumentWriter(self.client)
        writer.register(
            100000001,
            InstrumentRegistration(
                source_ticker="600000.SH",
                ticker="600000",
                name="Stock",
                exchange="SSE",
                asset_class="stock",
                list_date="1999-11-10",
                extension=StockExtension(
                    instrument_id=100000001,
                    list_status="L",
                    industry_id=801010,
                ),
            ),
        )
        writer.register(
            200000001,
            InstrumentRegistration(
                source_ticker="510300.SH",
                ticker="510300",
                name="ETF",
                exchange="SSE",
                asset_class="etf",
                list_date="2012-05-28",
                extension=ETFExtension(
                    instrument_id=200000001,
                    fund_type="equity",
                    fund_manager="Manager",
                    establish_date="2012-05-28",
                    tracking_index="000300.SH",
                ),
            ),
        )
        writer.register(
            300000001,
            InstrumentRegistration(
                source_ticker="000300.SH",
                ticker="000300",
                name="Index",
                exchange="SSE",
                asset_class="index",
                list_date="2005-04-08",
                extension=IndexExtension(
                    instrument_id=300000001,
                    base_date="2004-12-31",
                    base_point=1000.0,
                    num_constituents=300,
                ),
            ),
        )

        stock = self.reader.find_securities_with_extensions(asset_class="stock")
        etf = self.reader.find_securities_with_extensions(
            asset_class="etf",
            exchange="SSE",
        )
        index = self.reader.find_securities_with_extensions(
            asset_class="index",
            is_active=None,
        )

        assert stock["list_status"].to_list() == ["L"]
        assert etf["fund_type"].to_list() == ["equity"]
        assert index["base_point"].to_list() == [1000.0]

    def test_find_securities_with_extensions_without_join_and_empty_result(
        self,
    ) -> None:
        """Extension query handles no asset class and no matching rows."""
        self.client.execute("""
            INSERT INTO instrument (
                instrument_id, ticker, name, exchange, asset_class, list_date, is_active
            )
            VALUES (100000001, '600000', 'Stock', 'SSE', 'stock', '1999-11-10', TRUE)
        """)
        self.client.commit()

        all_rows = self.reader.find_securities_with_extensions(asset_class=None)
        missing = self.reader.find_securities_with_extensions(asset_class="bond")

        assert len(all_rows) == 1
        assert missing.is_empty()

    def teardown_method(self) -> None:
        """Clean up after test."""
        # No cleanup needed for in-memory database
        pass


@pytest.mark.integration
class TestInstrumentWriter:
    """
    Tests for InstrumentWriter.

    PIT (Pipeline Integration Tests) - tests complete data ingestion flow.
    These tests require more resources and time than unit tests.
    """

    @pytest.fixture(autouse=True)
    def setup(self, sqlite_client: SQLiteClient) -> None:
        """使用 fixture 自动注入已初始化的数据库客户端."""
        self.client = sqlite_client
        self.reader = InstrumentReader(self.client)
        self.writer = InstrumentWriter(self.client)

    def test_register_new_security(self) -> None:
        """Test registering a new instrument."""
        instrument_id = self.writer.register(
            instrument_id=100000001,
            registration=InstrumentRegistration(
                source_ticker="600000.SH",
                ticker="600000",
                name="Test Bank",
                exchange="SSE",
                asset_class="stock",
                list_date="1999-11-10",
            ),
        )

        assert instrument_id == 100000001

        # Verify instrument was inserted
        instrument = self.reader.get_by_instrument_id(instrument_id)
        assert instrument is not None
        assert instrument["ticker"] == "600000"
        assert instrument["name"] == "Test Bank"

        # Verify mapping was inserted
        resolved_sid = self.reader.resolve_instrument_id(
            "600000.SH", "tushare", asof=None
        )
        assert resolved_sid == instrument_id

    def test_register_invalidates_negative_cache(self) -> None:
        """Test that register() invalidates negative cache for new instrument."""
        # Create writer with DataCache
        data_cache = DataCache(ttl_seconds=300, max_size=1000, enable_metrics=False)
        reader_with_cache = InstrumentReader(self.client, cache=data_cache)
        writer_with_cache = InstrumentWriter(self.client, cache=data_cache)

        # First query: instrument doesn't exist, returns None (cached as -1)
        sid1 = reader_with_cache.resolve_instrument_id(
            "600999.SH", "tushare", asof=None
        )
        assert sid1 is None

        # Verify negative cache is set (still returns None without DB query)
        sid2 = reader_with_cache.resolve_instrument_id(
            "600999.SH", "tushare", asof=None
        )
        assert sid2 is None

        # Register the new instrument
        new_sid = writer_with_cache.register(
            instrument_id=100999001,
            registration=InstrumentRegistration(
                source_ticker="600999.SH",
                ticker="600999",
                name="New Stock",
                exchange="SSE",
                asset_class="stock",
                list_date="2020-01-01",
            ),
        )

        # After registration, negative cache should be invalidated
        # This should now return the newly registered instrument_id
        sid3 = reader_with_cache.resolve_instrument_id(
            "600999.SH", "tushare", asof=None
        )
        assert sid3 == new_sid

    def test_register_invalidates_instrument_id_ticker_map_cache(self) -> None:
        """Test that register() invalidates instrument_id_ticker_map cache."""
        # Create writer with DataCache
        data_cache = DataCache(ttl_seconds=300, max_size=1000, enable_metrics=False)
        reader_with_cache = InstrumentReader(self.client, cache=data_cache)
        writer_with_cache = InstrumentWriter(self.client, cache=data_cache)

        # Query instrument_id_ticker_map (should be empty)
        map1 = reader_with_cache.get_instrument_id_ticker_map()
        assert len(map1) == 0

        # Register a new instrument
        writer_with_cache.register(
            instrument_id=100999002,
            registration=InstrumentRegistration(
                source_ticker="600998.SH",
                ticker="600998",
                name="Another Stock",
                exchange="SSE",
                asset_class="stock",
                list_date="2020-01-01",
            ),
        )

        # After registration, instrument_id_ticker_map cache should be invalidated
        # This should now return the newly registered instrument
        map2 = reader_with_cache.get_instrument_id_ticker_map()
        assert len(map2) == 1
        assert 100999002 in map2
        assert map2[100999002] == "600998"

    def test_register_logs_error_on_exception(self, mocker: MockerFixture) -> None:
        """Test register logs error with error_type and error_message on exception."""
        # Mock client.commit to raise an exception
        with mocker.patch.object(
            self.client, "commit", side_effect=RuntimeError("DB error")
        ):
            mock_logger = mocker.patch(
                "ditto_data.storage.metadata.instrument.instrument_writer.logger"
            )

            with pytest.raises(RuntimeError):
                self.writer.register(
                    instrument_id=100000001,
                    registration=InstrumentRegistration(
                        source_ticker="600000.SH",
                        ticker="600000",
                        name="Test Bank",
                        exchange="SSE",
                        asset_class="stock",
                        list_date="1999-11-10",
                    ),
                )

            # Verify logger.error was called with error_type and error_message
            mock_logger.error.assert_called_once()
            call_kwargs = mock_logger.error.call_args.kwargs
            assert "error_type" in call_kwargs
            assert "error_message" in call_kwargs
            assert call_kwargs["event"] == "instrument_register_failed"
            assert call_kwargs["error_type"] == "RuntimeError"


@pytest.mark.integration
class TestSqlInjectionProtection:
    """
    Tests for SQL injection protection in IN clause construction.

    PIT (Pipeline Integration Tests) - tests complete data ingestion flow.
    These tests require more resources and time than unit tests.
    """

    @pytest.fixture(autouse=True)
    def setup(self, sqlite_client: SQLiteClient) -> None:
        """使用 fixture 自动注入已初始化的数据库客户端."""
        self.client = sqlite_client
        self.reader = InstrumentReader(self.client)

    def test_build_in_clause_empty_and_chunked(self) -> None:
        """IN clause helper should be safe for empty and chunked inputs."""
        empty_clause, empty_params = _build_in_clause("instrument_id", [])
        chunked_clause, chunked_params = _build_in_clause(
            "instrument_id",
            [1, 2, 3, 4, 5],
            chunk_size=2,
        )

        assert empty_clause == "1=0"
        assert empty_params == []
        assert chunked_clause == (
            "(instrument_id IN (?,?) OR instrument_id IN (?,?) OR instrument_id IN (?))"
        )
        assert chunked_params == [1, 2, 3, 4, 5]

    def test_in_clause_with_many_sids(self) -> None:
        """Test IN clause handles large list of SIDs safely."""
        # Insert test data for 100 securities
        for i in range(100):
            instrument_id = 100000001 + i
            self.client.execute(
                """INSERT INTO instrument
                (
                    instrument_id, ticker, name, exchange, asset_class,
                    list_date, is_active
                )
                VALUES (?, ?, ?, ?, ?, ?, TRUE)""",
                [
                    instrument_id,
                    f"60{i:04d}",
                    f"Stock{i}",
                    "SSE",
                    "stock",
                    "2000-01-01",
                ],
            )
        self.client.commit()

        # Query with 100 SIDs
        instrument_ids = list(range(100000001, 100000101))
        result = self.reader.find_securities(
            SecurityQuery(instrument_ids=instrument_ids),
        )

        # Should return all 100 securities
        assert len(result) == 100

    def test_in_clause_with_single_sid(self) -> None:
        """Test IN clause works with single Instrument ID."""
        self.client.execute(
            """INSERT INTO instrument
            (instrument_id, ticker, name, exchange, asset_class, list_date, is_active)
            VALUES (100000001, '600000', 'Test', 'SSE', 'stock', '2000-01-01', TRUE)"""
        )
        self.client.commit()

        result = self.reader.find_securities(
            SecurityQuery(instrument_ids=[100000001]),
        )
        assert len(result) == 1
        assert result["instrument_id"][0] == 100000001

    def test_get_instrument_id_ticker_map_with_many_instrument_ids(self) -> None:
        """Test get_instrument_id_ticker_map with large list."""
        # Insert test data for 50 securities
        for i in range(50):
            instrument_id = 100000001 + i
            self.client.execute(
                """INSERT INTO instrument
                (
                    instrument_id, ticker, name, exchange, asset_class,
                    list_date, is_active
                )
                VALUES (?, ?, ?, ?, ?, ?, TRUE)""",
                [
                    instrument_id,
                    f"60{i:04d}",
                    f"Stock{i}",
                    "SSE",
                    "stock",
                    "2000-01-01",
                ],
            )
        self.client.commit()

        # Query with 50 instrument_ids
        instrument_ids = list(range(100000001, 100000051))
        mapping = self.reader.get_instrument_id_ticker_map(instrument_ids)

        # Should return all 50 mappings
        assert len(mapping) == 50
        assert mapping[100000001] == "600000"
        assert mapping[100000050] == "600049"  # i=49 produces "600049"

    def test_special_characters_in_source_ticker(self) -> None:
        """Test special characters in source_ticker are handled safely."""
        self.client.execute(
            """INSERT INTO instrument
            (instrument_id, ticker, name, exchange, asset_class, list_date)
            VALUES (100000001, 'TEST', 'Test', 'SSE', 'stock', '2000-01-01')"""
        )
        # Use source_ticker with special characters that could be SQL injection attempts
        self.client.execute(
            """INSERT INTO instrument_mapping
            (instrument_id, source, source_ticker, effective_from)
            VALUES (100000001, 'tushare', 'test;DROP TABLE instrument--', '2000-01-01')
            """
        )
        self.client.commit()

        # Should safely query without executing the injection
        instrument_id = self.reader.resolve_instrument_id(
            "test;DROP TABLE instrument--", "tushare", asof=None
        )
        assert instrument_id == 100000001

        # Verify the instrument table still exists
        result = self.client.fetchall("SELECT COUNT(*) as count FROM instrument")
        assert result[0]["count"] >= 1
