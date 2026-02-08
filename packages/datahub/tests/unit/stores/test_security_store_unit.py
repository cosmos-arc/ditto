"""Tests for InstrumentStore."""

import polars as pl
import pytest
from ditto_datahub.stores.metadata.instrument import (
    InstrumentRegistration,
    InstrumentStore,
)
from ditto_datahub.stores.sqlite_client import SQLiteClient
from ditto_foundation.cache import DataCache
from pytest_mock import MockerFixture


@pytest.mark.integration
class TestInstrumentStore:
    """
    Tests for InstrumentStore.

    PIT (Pipeline Integration Tests) - tests complete data ingestion flow.
    These tests require more resources and time than unit tests.
    """

    @pytest.fixture(autouse=True)
    def setup(self, sqlite_client: SQLiteClient) -> None:
        """使用 fixture 自动注入已初始化的数据库客户端."""
        self.client = sqlite_client
        self.store = InstrumentStore(self.client)

    def test_resolve_instrument_id_current_mapping(self) -> None:
        """Test resolving instrument_id for current mapping."""
        # Insert test data
        self.client.execute("""
            INSERT INTO instrument (
                instrument_id, symbol, name, exchange, asset_class, list_date
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
        instrument_id = self.store.resolve_instrument_id(
            "600000.SH", "tushare", asof=None
        )
        assert instrument_id == 100000001

    def test_resolve_instrument_id_with_pit(self) -> None:
        """Test resolving instrument_id with PIT (asof parameter)."""
        # Insert test data with historical mapping
        self.client.execute("""
            INSERT INTO instrument (
                instrument_id, symbol, name, exchange, asset_class, list_date
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
        instrument_id = self.store.resolve_instrument_id(
            "000022.SZ", "tushare", asof="2017-01-01"
        )
        assert instrument_id == 100000001

        # Query after expiration - should return None
        instrument_id = self.store.resolve_instrument_id(
            "000022.SZ", "tushare", asof="2019-01-01"
        )
        assert instrument_id is None

    def test_resolve_instrument_id_cached(self) -> None:
        """Test that resolve_instrument_id uses DataCache for current queries."""
        # Create store with DataCache
        data_cache = DataCache(ttl_seconds=300, max_size=1000, enable_metrics=False)
        store_with_cache = InstrumentStore(self.client, data_cache=data_cache)

        self.client.execute("""
            INSERT INTO instrument (
                instrument_id, symbol, name, exchange, asset_class, list_date
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
        sid1 = store_with_cache.resolve_instrument_id("600000.SH", "tushare", asof=None)
        assert sid1 == 100000001

        # Second call - cache hit
        sid2 = store_with_cache.resolve_instrument_id("600000.SH", "tushare", asof=None)
        assert sid2 == 100000001

        # PIT 查询也应该被缓存
        sid3 = store_with_cache.resolve_instrument_id(
            "600000.SH", "tushare", asof="2020-01-01"
        )
        assert sid3 == 100000001

    def test_resolve_instrument_ids_batch(self) -> None:
        """Test batch resolution of source_tickers to instrument_ids."""
        # Insert test data
        for i, code in enumerate(["600000.SH", "600001.SH", "600002.SH"]):
            instrument_id = 100000001 + i
            sql = (
                "INSERT INTO instrument "
                "(instrument_id, symbol, name, exchange, asset_class, list_date) "
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
        result = self.store.resolve_instrument_ids_batch(
            ["600000.SH", "600001.SH", "600003.SH"],  # 600003 doesn't exist
            source="tushare",
            asof=None,
        )

        assert result["600000.SH"] == 100000001
        assert result["600001.SH"] == 100000002
        assert "600003.SH" not in result  # Not found

    def test_get_by_sid(self) -> None:
        """Test getting instrument by instrument_id."""
        sql = (
            "INSERT INTO instrument "
            "(instrument_id, symbol, name, exchange, "
            "asset_class, list_date, is_active) "
            "VALUES (100000001, '600000', 'Test Bank', 'SSE', 'stock', "
            "'1999-11-10', TRUE)"
        )
        self.client.execute(sql)
        self.client.commit()

        result = self.store.get_by_instrument_id(100000001)
        assert result is not None
        assert result["instrument_id"] == 100000001
        assert result["symbol"] == "600000"
        assert result["name"] == "Test Bank"

    def test_get_by_sid_not_found(self) -> None:
        """Test getting non-existent instrument_id returns None."""
        result = self.store.get_by_instrument_id(999999999)
        assert result is None

    def test_get_source_ticker(self) -> None:
        """Test reverse lookup: instrument_id to source_ticker."""
        self.client.execute("""
            INSERT INTO instrument (
                instrument_id, symbol, name, exchange, asset_class, list_date
            )
            VALUES (100000001, '600000', 'Test', 'SSE', 'stock', '1999-11-10')
        """)
        self.client.execute("""
            INSERT INTO instrument_mapping
            (instrument_id, source, source_ticker, effective_from)
            VALUES (100000001, 'tushare', '600000.SH', '1999-11-10')
        """)
        self.client.commit()

        source_ticker = self.store.get_source_ticker(100000001, "tushare", asof=None)
        assert source_ticker == "600000.SH"

    def test_list_sids(self) -> None:
        """Test listing all instrument_ids with filters."""
        # Insert test data
        for i in range(3):
            instrument_id = 100000001 + i
            exchange = "SSE" if i < 2 else "SZSE"
            sql = (
                "INSERT INTO instrument "
                "(instrument_id, symbol, name, exchange, "
                "asset_class, list_date, is_active) "
                f"VALUES ({instrument_id}, '60{i:04d}', 'Stock{i}', '{exchange}', "
                "'stock', "
                "'2000-01-01', TRUE)"
            )
            self.client.execute(sql)

        self.client.commit()

        # List all
        all_sids = self.store.list_instrument_ids()
        assert len(all_sids) == 3

        # Filter by exchange
        sse_sids = self.store.list_instrument_ids(exchange="SSE")
        assert len(sse_sids) == 2
        assert 100000001 in sse_sids
        assert 100000002 in sse_sids

    def test_list_sids_with_is_active_none(self) -> None:
        """Test listing with is_active=None returns active and inactive rows."""
        # Insert test data: 2 active, 1 inactive
        for i in range(3):
            instrument_id = 100000001 + i
            is_active = "TRUE" if i < 2 else "FALSE"
            sql = (
                "INSERT INTO instrument "
                "(instrument_id, symbol, name, exchange, "
                "asset_class, list_date, is_active) "
                f"VALUES ({instrument_id}, '60{i:04d}', 'Stock{i}', 'SSE', 'stock', "
                f"'2000-01-01', {is_active})"
            )
            self.client.execute(sql)

        self.client.commit()

        # Default (is_active=True) should return only active
        active_sids = self.store.list_instrument_ids()
        assert len(active_sids) == 2
        assert 100000001 in active_sids
        assert 100000002 in active_sids
        assert 100000003 not in active_sids

        # is_active=False should return only inactive
        inactive_sids = self.store.list_instrument_ids(is_active=False)
        assert len(inactive_sids) == 1
        assert 100000003 in inactive_sids

        # is_active=None should return ALL (both active and inactive)
        all_sids = self.store.list_instrument_ids(is_active=None)
        assert len(all_sids) == 3
        assert 100000001 in all_sids
        assert 100000002 in all_sids
        assert 100000003 in all_sids

    def test_get_symbol(self) -> None:
        """Test getting symbol by instrument_id."""
        self.client.execute("""
            INSERT INTO instrument (
                instrument_id, symbol, name, exchange, asset_class, list_date
            )
            VALUES (100000001, '600000', 'Test', 'SSE', 'stock', '1999-11-10')
        """)
        self.client.commit()

        symbol = self.store.get_symbol(100000001)
        assert symbol == "600000"

    def test_get_instrument_id_symbol_map(self) -> None:
        """Test getting batch instrument_id to symbol mapping."""
        # Insert test data
        for i in range(3):
            instrument_id = 100000001 + i
            sql = (
                "INSERT INTO instrument "
                "(instrument_id, symbol, name, exchange, "
                "asset_class, list_date, is_active) "
                f"VALUES ({instrument_id}, '60{i:04d}', 'Stock{i}', 'SSE', 'stock', "
                "'2000-01-01', TRUE)"
            )
            self.client.execute(sql)

        self.client.commit()

        mapping = self.store.get_instrument_id_symbol_map()
        assert len(mapping) == 3
        assert mapping[100000001] == "600000"
        assert mapping[100000002] == "600001"

    def test_enrich_with_symbol(self) -> None:
        """Test enriching DataFrame with symbol column."""
        # Insert test data
        self.client.execute("""
            INSERT INTO instrument (
                instrument_id, symbol, name, exchange, asset_class, list_date
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
        result = self.store.enrich_with_symbol(df)

        assert "symbol" in result.columns
        assert result["symbol"].to_list() == ["600000", "600000"]

    def test_enrich_with_symbol_empty_df(self) -> None:
        """Test enriching empty DataFrame returns empty."""
        df = pl.DataFrame(schema={"instrument_id": pl.Int64, "close": pl.Float64})
        result = self.store.enrich_with_symbol(df)
        assert result.is_empty()

    def test_find_securities(self) -> None:
        """Test finding securities with various filters."""
        # Insert test data
        self.client.execute("""
            INSERT INTO instrument
            (instrument_id, symbol, name, exchange, asset_class, list_date, is_active)
            VALUES (100000001, '600000', 'Bank', 'SSE', 'stock', '1999-11-10', TRUE)
        """)
        self.client.execute("""
            INSERT INTO instrument_mapping
            (instrument_id, source, source_ticker, effective_from)
            VALUES (100000001, 'tushare', '600000.SH', '1999-11-10')
        """)
        self.client.commit()

        # Find by source_ticker
        result = self.store.find_securities(
            source_tickers=["600000.SH"], source="tushare"
        )
        assert len(result) == 1
        assert result["instrument_id"][0] == 100000001

        # Find by asset_class
        result = self.store.find_securities(asset_class="stock")
        assert len(result) == 1

    def test_register_new_security(self) -> None:
        """Test registering a new instrument."""
        instrument_id = self.store.register(
            instrument_id=100000001,
            registration=InstrumentRegistration(
                source_ticker="600000.SH",
                symbol="600000",
                name="Test Bank",
                exchange="SSE",
                asset_class="stock",
                list_date="1999-11-10",
            ),
        )

        assert instrument_id == 100000001

        # Verify instrument was inserted
        instrument = self.store.get_by_instrument_id(instrument_id)
        assert instrument is not None
        assert instrument["symbol"] == "600000"
        assert instrument["name"] == "Test Bank"

        # Verify mapping was inserted
        resolved_sid = self.store.resolve_instrument_id(
            "600000.SH", "tushare", asof=None
        )
        assert resolved_sid == instrument_id

    def test_register_invalidates_negative_cache(self) -> None:
        """Test that register() invalidates negative cache for new instrument."""
        # Create store with DataCache
        data_cache = DataCache(ttl_seconds=300, max_size=1000, enable_metrics=False)
        store_with_cache = InstrumentStore(self.client, data_cache=data_cache)

        # First query: instrument doesn't exist, returns None (cached as -1)
        sid1 = store_with_cache.resolve_instrument_id("600999.SH", "tushare", asof=None)
        assert sid1 is None

        # Verify negative cache is set (still returns None without DB query)
        sid2 = store_with_cache.resolve_instrument_id("600999.SH", "tushare", asof=None)
        assert sid2 is None

        # Register the new instrument
        new_sid = store_with_cache.register(
            instrument_id=100999001,
            registration=InstrumentRegistration(
                source_ticker="600999.SH",
                symbol="600999",
                name="New Stock",
                exchange="SSE",
                asset_class="stock",
                list_date="2020-01-01",
            ),
        )

        # After registration, negative cache should be invalidated
        # This should now return the newly registered instrument_id
        sid3 = store_with_cache.resolve_instrument_id("600999.SH", "tushare", asof=None)
        assert sid3 == new_sid

    def test_register_invalidates_instrument_id_symbol_map_cache(self) -> None:
        """Test that register() invalidates instrument_id_symbol_map cache."""
        # Create store with DataCache
        data_cache = DataCache(ttl_seconds=300, max_size=1000, enable_metrics=False)
        store_with_cache = InstrumentStore(self.client, data_cache=data_cache)

        # Query instrument_id_symbol_map (should be empty)
        map1 = store_with_cache.get_instrument_id_symbol_map()
        assert len(map1) == 0

        # Register a new instrument
        store_with_cache.register(
            instrument_id=100999002,
            registration=InstrumentRegistration(
                source_ticker="600998.SH",
                symbol="600998",
                name="Another Stock",
                exchange="SSE",
                asset_class="stock",
                list_date="2020-01-01",
            ),
        )

        # After registration, instrument_id_symbol_map cache should be invalidated
        # This should now return the newly registered instrument
        map2 = store_with_cache.get_instrument_id_symbol_map()
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
                "ditto_datahub.domains.metadata.instrument.instrument_store.logger"
            )

            with pytest.raises(RuntimeError):
                self.store.register(
                    instrument_id=100000001,
                    registration=InstrumentRegistration(
                        source_ticker="600000.SH",
                        symbol="600000",
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

    def teardown_method(self) -> None:
        """Clean up after test."""
        # No cleanup needed for in-memory database
        pass


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
        self.store = InstrumentStore(self.client)

    def test_in_clause_with_many_sids(self) -> None:
        """Test IN clause handles large list of SIDs safely."""
        # Insert test data for 100 securities
        for i in range(100):
            instrument_id = 100000001 + i
            self.client.execute(
                """INSERT INTO instrument
                (
                    instrument_id, symbol, name, exchange, asset_class,
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
        result = self.store.find_securities(instrument_ids=instrument_ids)

        # Should return all 100 securities
        assert len(result) == 100

    def test_in_clause_with_single_sid(self) -> None:
        """Test IN clause works with single Instrument ID."""
        self.client.execute(
            """INSERT INTO instrument
            (instrument_id, symbol, name, exchange, asset_class, list_date, is_active)
            VALUES (100000001, '600000', 'Test', 'SSE', 'stock', '2000-01-01', TRUE)"""
        )
        self.client.commit()

        result = self.store.find_securities(instrument_ids=[100000001])
        assert len(result) == 1
        assert result["instrument_id"][0] == 100000001

    def test_get_instrument_id_symbol_map_with_many_instrument_ids(self) -> None:
        """Test get_instrument_id_symbol_map with large list."""
        # Insert test data for 50 securities
        for i in range(50):
            instrument_id = 100000001 + i
            self.client.execute(
                """INSERT INTO instrument
                (
                    instrument_id, symbol, name, exchange, asset_class,
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
        mapping = self.store.get_instrument_id_symbol_map(instrument_ids)

        # Should return all 50 mappings
        assert len(mapping) == 50
        assert mapping[100000001] == "600000"
        assert mapping[100000050] == "600049"  # i=49 produces "600049"

    def test_special_characters_in_source_ticker(self) -> None:
        """Test special characters in source_ticker are handled safely."""
        self.client.execute(
            """INSERT INTO instrument
            (instrument_id, symbol, name, exchange, asset_class, list_date)
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
        instrument_id = self.store.resolve_instrument_id(
            "test;DROP TABLE instrument--", "tushare", asof=None
        )
        assert instrument_id == 100000001

        # Verify the instrument table still exists
        result = self.client.fetchall("SELECT COUNT(*) as count FROM instrument")
        assert result[0]["count"] >= 1
