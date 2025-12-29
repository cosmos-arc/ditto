"""Tests for SecurityStore."""

import polars as pl
from ditto_datahub.runtime.cache import DataCache
from ditto_datahub.runtime.sqlite_pool import SQLitePool
from ditto_datahub.stores.security_store import SecurityStore
from ditto_datahub.stores.sqlite_client import SQLiteClient


class TestSecurityStore:
    """Tests for SecurityStore."""

    def setup_method(self) -> None:
        """Set up test database."""
        # Create in-memory database for testing
        self.pool = SQLitePool(":memory:")
        self.pool.init_schema()
        self.client = SQLiteClient(self.pool)
        self.store = SecurityStore(self.client)

    def test_resolve_sid_current_mapping(self) -> None:
        """Test resolving sid for current mapping."""
        # Insert test data
        self.client.execute("""
            INSERT INTO security (sid, symbol, name, exchange, asset_class, list_date)
            VALUES (100000001, '600000', '浦发银行', 'SSE', 'stock', '1999-11-10')
        """)
        self.client.execute("""
            INSERT INTO security_mapping
            (sid, source, src_code, effective_from)
            VALUES (100000001, 'tushare', '600000.SH', '1999-11-10')
        """)
        self.client.commit()

        # Test resolve
        sid = self.store.resolve_sid("600000.SH", "tushare", asof=None)
        assert sid == 100000001

    def test_resolve_sid_with_pit(self) -> None:
        """Test resolving sid with PIT (asof parameter)."""
        # Insert test data with historical mapping
        self.client.execute("""
            INSERT INTO security (sid, symbol, name, exchange, asset_class, list_date)
            VALUES (100000001, '000022', '深赤湾A', 'SZSE', 'stock', '1990-01-01')
        """)
        # Mapping valid until 2018-12-25
        self.client.execute("""
            INSERT INTO security_mapping
            (sid, source, src_code, effective_from, effective_to)
            VALUES (100000001, 'tushare', '000022.SZ', '1990-01-01', '2018-12-25')
        """)
        self.client.commit()

        # Query before expiration
        sid = self.store.resolve_sid("000022.SZ", "tushare", asof="2017-01-01")
        assert sid == 100000001

        # Query after expiration - should return None
        sid = self.store.resolve_sid("000022.SZ", "tushare", asof="2019-01-01")
        assert sid is None

    def test_resolve_sid_cached(self) -> None:
        """Test that resolve_sid uses DataCache for current queries."""
        # Create store with DataCache
        data_cache = DataCache(ttl_seconds=300, max_size=1000, enable_metrics=False)
        store_with_cache = SecurityStore(self.client, data_cache=data_cache)

        self.client.execute("""
            INSERT INTO security (sid, symbol, name, exchange, asset_class, list_date)
            VALUES (100000001, '600000', 'Test', 'SSE', 'stock', '1999-11-10')
        """)
        self.client.execute("""
            INSERT INTO security_mapping
            (sid, source, src_code, effective_from)
            VALUES (100000001, 'tushare', '600000.SH', '1999-11-10')
        """)
        self.client.commit()

        # First call - cache miss
        sid1 = store_with_cache.resolve_sid("600000.SH", "tushare", asof=None)
        assert sid1 == 100000001

        # Second call - cache hit
        sid2 = store_with_cache.resolve_sid("600000.SH", "tushare", asof=None)
        assert sid2 == 100000001

        # PIT 查询也应该被缓存
        sid3 = store_with_cache.resolve_sid("600000.SH", "tushare", asof="2020-01-01")
        assert sid3 == 100000001

    def test_resolve_sids_batch(self) -> None:
        """Test batch resolution of src_codes to sids."""
        # Insert test data
        for i, code in enumerate(["600000.SH", "600001.SH", "600002.SH"]):
            sid = 100000001 + i
            sql = (
                "INSERT INTO security "
                "(sid, symbol, name, exchange, asset_class, list_date) "
                f"VALUES ({sid}, '60000{i}', 'Stock{i}', 'SSE', 'stock', '2000-01-01')"
            )
            self.client.execute(sql)

            sql = (
                "INSERT INTO security_mapping "
                "(sid, source, src_code, effective_from) "
                f"VALUES ({sid}, 'tushare', '{code}', '2000-01-01')"
            )
            self.client.execute(sql)

        self.client.commit()

        # Test batch resolve
        result = self.store.resolve_sids_batch(
            ["600000.SH", "600001.SH", "600003.SH"],  # 600003 doesn't exist
            source="tushare",
            asof=None,
        )

        assert result["600000.SH"] == 100000001
        assert result["600001.SH"] == 100000002
        assert "600003.SH" not in result  # Not found

    def test_get_by_sid(self) -> None:
        """Test getting security by sid."""
        sql = (
            "INSERT INTO security "
            "(sid, symbol, name, exchange, asset_class, list_date, is_active) "
            "VALUES (100000001, '600000', 'Test Bank', 'SSE', 'stock', "
            "'1999-11-10', TRUE)"
        )
        self.client.execute(sql)
        self.client.commit()

        result = self.store.get_by_sid(100000001)
        assert result is not None
        assert result["sid"] == 100000001
        assert result["symbol"] == "600000"
        assert result["name"] == "Test Bank"

    def test_get_by_sid_not_found(self) -> None:
        """Test getting non-existent sid returns None."""
        result = self.store.get_by_sid(999999999)
        assert result is None

    def test_get_src_code(self) -> None:
        """Test reverse lookup: sid to src_code."""
        self.client.execute("""
            INSERT INTO security (sid, symbol, name, exchange, asset_class, list_date)
            VALUES (100000001, '600000', 'Test', 'SSE', 'stock', '1999-11-10')
        """)
        self.client.execute("""
            INSERT INTO security_mapping
            (sid, source, src_code, effective_from)
            VALUES (100000001, 'tushare', '600000.SH', '1999-11-10')
        """)
        self.client.commit()

        src_code = self.store.get_src_code(100000001, "tushare", asof=None)
        assert src_code == "600000.SH"

    def test_list_sids(self) -> None:
        """Test listing all sids with filters."""
        # Insert test data
        for i in range(3):
            sid = 100000001 + i
            exchange = "SSE" if i < 2 else "SZSE"
            sql = (
                "INSERT INTO security "
                "(sid, symbol, name, exchange, asset_class, list_date, is_active) "
                f"VALUES ({sid}, '60{i:04d}', 'Stock{i}', '{exchange}', 'stock', "
                "'2000-01-01', TRUE)"
            )
            self.client.execute(sql)

        self.client.commit()

        # List all
        all_sids = self.store.list_sids()
        assert len(all_sids) == 3

        # Filter by exchange
        sse_sids = self.store.list_sids(exchange="SSE")
        assert len(sse_sids) == 2
        assert 100000001 in sse_sids
        assert 100000002 in sse_sids

    def test_get_symbol(self) -> None:
        """Test getting symbol by sid."""
        self.client.execute("""
            INSERT INTO security (sid, symbol, name, exchange, asset_class, list_date)
            VALUES (100000001, '600000', 'Test', 'SSE', 'stock', '1999-11-10')
        """)
        self.client.commit()

        symbol = self.store.get_symbol(100000001)
        assert symbol == "600000"

    def test_get_sid_symbol_map(self) -> None:
        """Test getting batch sid to symbol mapping."""
        # Insert test data
        for i in range(3):
            sid = 100000001 + i
            sql = (
                "INSERT INTO security "
                "(sid, symbol, name, exchange, asset_class, list_date, is_active) "
                f"VALUES ({sid}, '60{i:04d}', 'Stock{i}', 'SSE', 'stock', "
                "'2000-01-01', TRUE)"
            )
            self.client.execute(sql)

        self.client.commit()

        mapping = self.store.get_sid_symbol_map()
        assert len(mapping) == 3
        assert mapping[100000001] == "600000"
        assert mapping[100000002] == "600001"

    def test_enrich_with_symbol(self) -> None:
        """Test enriching DataFrame with symbol column."""
        # Insert test data
        self.client.execute("""
            INSERT INTO security (sid, symbol, name, exchange, asset_class, list_date)
            VALUES (100000001, '600000', 'Test', 'SSE', 'stock', '1999-11-10')
        """)
        self.client.commit()

        # Create test DataFrame
        df = pl.DataFrame(
            {
                "sid": [100000001, 100000001],
                "close": [10.5, 11.0],
            }
        )

        # Enrich
        result = self.store.enrich_with_symbol(df)

        assert "symbol" in result.columns
        assert result["symbol"].to_list() == ["600000", "600000"]

    def test_enrich_with_symbol_empty_df(self) -> None:
        """Test enriching empty DataFrame returns empty."""
        df = pl.DataFrame(schema={"sid": pl.Int64, "close": pl.Float64})
        result = self.store.enrich_with_symbol(df)
        assert result.is_empty()

    def test_find_securities(self) -> None:
        """Test finding securities with various filters."""
        # Insert test data
        self.client.execute("""
            INSERT INTO security
            (sid, symbol, name, exchange, asset_class, list_date, is_active)
            VALUES (100000001, '600000', 'Bank', 'SSE', 'stock', '1999-11-10', TRUE)
        """)
        self.client.execute("""
            INSERT INTO security_mapping
            (sid, source, src_code, effective_from)
            VALUES (100000001, 'tushare', '600000.SH', '1999-11-10')
        """)
        self.client.commit()

        # Find by src_code
        result = self.store.find_securities(src_codes=["600000.SH"], source="tushare")
        assert len(result) == 1
        assert result["sid"][0] == 100000001

        # Find by asset_class
        result = self.store.find_securities(asset_class="stock")
        assert len(result) == 1

    def test_register_new_security(self) -> None:
        """Test registering a new security."""
        sid = self.store.register(
            sid=100000001,
            source="tushare",
            src_code="600000.SH",
            symbol="600000",
            name="Test Bank",
            exchange="SSE",
            asset_class="stock",
            list_date="1999-11-10",
        )

        assert sid == 100000001

        # Verify security was inserted
        security = self.store.get_by_sid(sid)
        assert security is not None
        assert security["symbol"] == "600000"
        assert security["name"] == "Test Bank"

        # Verify mapping was inserted
        resolved_sid = self.store.resolve_sid("600000.SH", "tushare", asof=None)
        assert resolved_sid == sid

    def teardown_method(self) -> None:
        """Clean up after test."""
        # No cleanup needed for in-memory database
        pass


class TestSqlInjectionProtection:
    """Tests for SQL injection protection in IN clause construction."""

    def setup_method(self) -> None:
        """Set up test database."""
        self.pool = SQLitePool(":memory:")
        self.pool.init_schema()
        self.client = SQLiteClient(self.pool)
        self.store = SecurityStore(self.client)

    def test_in_clause_with_many_sids(self) -> None:
        """Test IN clause handles large list of SIDs safely."""
        # Insert test data for 100 securities
        for i in range(100):
            sid = 100000001 + i
            self.client.execute(
                """INSERT INTO security
                (sid, symbol, name, exchange, asset_class, list_date, is_active)
                VALUES (?, ?, ?, ?, ?, ?, TRUE)""",
                [sid, f"60{i:04d}", f"Stock{i}", "SSE", "stock", "2000-01-01"],
            )
        self.client.commit()

        # Query with 100 SIDs
        sids = list(range(100000001, 100000101))
        result = self.store.find_securities(sids=sids)

        # Should return all 100 securities
        assert len(result) == 100

    def test_in_clause_with_single_sid(self) -> None:
        """Test IN clause works with single SID."""
        self.client.execute(
            """INSERT INTO security
            (sid, symbol, name, exchange, asset_class, list_date, is_active)
            VALUES (100000001, '600000', 'Test', 'SSE', 'stock', '2000-01-01', TRUE)"""
        )
        self.client.commit()

        result = self.store.find_securities(sids=[100000001])
        assert len(result) == 1
        assert result["sid"][0] == 100000001

    def test_get_sid_symbol_map_with_many_sids(self) -> None:
        """Test get_sid_symbol_map with large list."""
        # Insert test data for 50 securities
        for i in range(50):
            sid = 100000001 + i
            self.client.execute(
                """INSERT INTO security
                (sid, symbol, name, exchange, asset_class, list_date, is_active)
                VALUES (?, ?, ?, ?, ?, ?, TRUE)""",
                [sid, f"60{i:04d}", f"Stock{i}", "SSE", "stock", "2000-01-01"],
            )
        self.client.commit()

        # Query with 50 SIDs
        sids = list(range(100000001, 100000051))
        mapping = self.store.get_sid_symbol_map(sids)

        # Should return all 50 mappings
        assert len(mapping) == 50
        assert mapping[100000001] == "600000"
        assert mapping[100000050] == "600049"  # i=49 produces "600049"

    def test_special_characters_in_src_code(self) -> None:
        """Test special characters in src_code are handled safely."""
        self.client.execute(
            """INSERT INTO security
            (sid, symbol, name, exchange, asset_class, list_date)
            VALUES (100000001, 'TEST', 'Test', 'SSE', 'stock', '2000-01-01')"""
        )
        # Use src_code with special characters that could be SQL injection attempts
        self.client.execute(
            """INSERT INTO security_mapping
            (sid, source, src_code, effective_from)
            VALUES (100000001, 'tushare', 'test;DROP TABLE security--', '2000-01-01')"""
        )
        self.client.commit()

        # Should safely query without executing the injection
        sid = self.store.resolve_sid("test;DROP TABLE security--", "tushare", asof=None)
        assert sid == 100000001

        # Verify the security table still exists
        result = self.client.fetchall("SELECT COUNT(*) as count FROM security")
        assert result[0]["count"] >= 1
