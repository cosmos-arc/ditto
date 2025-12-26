"""Tests for SecurityRepository."""

from ditto_datahub.repositories.security import SecurityRepository
from ditto_datahub.runtime.sid_allocator import SidAllocator
from ditto_datahub.runtime.sqlite_pool import SQLitePool
from ditto_datahub.stores.security_store import SecurityStore
from ditto_datahub.stores.sqlite_client import SQLiteClient


class TestSecurityRepository:
    """Tests for SecurityRepository."""

    def setup_method(self) -> None:
        """Set up test database."""
        self.pool = SQLitePool(":memory:")
        self.pool.init_schema()
        self.client = SQLiteClient(self.pool)
        self.security_store = SecurityStore(self.client)
        self.sid_allocator = SidAllocator(self.pool)
        self.repo = SecurityRepository(
            self.security_store,
            self.sid_allocator,
        )

    def test_get_returns_securities_dataframe(self) -> None:
        """Test get returns securities as DataFrame."""
        # Arrange
        self.client.execute("""
            INSERT INTO security
            (sid, symbol, name, exchange, asset_class, list_date)
            VALUES (100000001, '600000', 'Bank', 'SSE', 'stock', '2000-01-01')
        """)
        self.client.execute("""
            INSERT INTO security_mapping
            (sid, source, src_code, effective_from)
            VALUES (100000001, 'tushare', '600000.SH', '2000-01-01')
        """)
        self.client.commit()

        # Act
        result = self.repo.get(sids=[100000001])

        # Assert
        assert len(result) == 1
        assert result["sid"][0] == 100000001
        assert result["symbol"][0] == "600000"

    def test_resolve_identifier_with_src_code(self) -> None:
        """Test resolve_identifier with src_code."""
        # Arrange
        self.client.execute("""
            INSERT INTO security
            (sid, symbol, name, exchange, asset_class, list_date)
            VALUES (100000001, '600000', 'Bank', 'SSE', 'stock', '2000-01-01')
        """)
        self.client.execute("""
            INSERT INTO security_mapping
            (sid, source, src_code, effective_from)
            VALUES (100000001, 'tushare', '600000.SH', '2000-01-01')
        """)
        self.client.commit()

        # Act
        sid = self.repo.resolve_identifier("600000.SH", "tushare")

        # Assert
        assert sid == 100000001

    def test_resolve_identifier_with_symbol(self) -> None:
        """Test resolve_identifier with symbol."""
        # Arrange
        self.client.execute("""
            INSERT INTO security
            (sid, symbol, name, exchange, asset_class, list_date)
            VALUES (100000001, '600000', 'Bank', 'SSE', 'stock', '2000-01-01')
        """)
        self.client.execute("""
            INSERT INTO security_mapping
            (sid, source, src_code, effective_from)
            VALUES (100000001, 'tushare', '600000.SH', '2000-01-01')
        """)
        self.client.commit()

        # Act
        sid = self.repo.resolve_identifier("600000", "tushare")

        # Assert
        assert sid == 100000001

    def test_resolve_identifier_not_found(self) -> None:
        """Test resolve_identifier returns None for unknown identifier."""
        # Act
        sid = self.repo.resolve_identifier("999999.SH", "tushare")

        # Assert
        assert sid is None

    def test_resolve_identifiers_batch(self) -> None:
        """Test batch resolution of identifiers."""
        # Arrange
        for i in range(3):
            sid = 100000001 + i
            self.client.execute(
                f"INSERT INTO security "
                f"(sid, symbol, name, exchange, asset_class, list_date) "
                f"VALUES ({sid}, '60{i:04d}', 'Stock{i}', 'SSE', 'stock', '2000-01-01')"
            )
            self.client.execute(
                f"INSERT INTO security_mapping "
                f"(sid, source, src_code, effective_from) "
                f"VALUES ({sid}, 'tushare', '60000{i}.SH', '2000-01-01')"
            )
        self.client.commit()

        # Act
        result = self.repo.resolve_identifiers_batch(
            ["600000.SH", "600001.SH", "600003.SH"],  # 600003 doesn't exist
            source="tushare",
        )

        # Assert
        assert result["600000.SH"] == 100000001
        assert result["600001.SH"] == 100000002
        assert "600003.SH" not in result  # Not found

    def test_get_by_sid(self) -> None:
        """Test getting security by sid."""
        # Arrange
        self.client.execute("""
            INSERT INTO security
            (sid, symbol, name, exchange, asset_class, list_date)
            VALUES (100000001, '600000', 'Test Bank', 'SSE', 'stock', '1999-11-10')
        """)
        self.client.commit()

        # Act
        result = self.repo.get_by_sid(100000001)

        # Assert
        assert result is not None
        assert result["sid"] == 100000001
        assert result["symbol"] == "600000"
        assert result["name"] == "Test Bank"

    def test_get_by_sid_not_found(self) -> None:
        """Test getting non-existent sid returns None."""
        # Act
        result = self.repo.get_by_sid(999999999)

        # Assert
        assert result is None

    def test_list_all(self) -> None:
        """Test listing all sids."""
        # Arrange
        for i in range(3):
            sid = 100000001 + i
            self.client.execute(
                "INSERT INTO security "
                "(sid, symbol, name, exchange, asset_class, list_date, is_active) "
                f"VALUES ({sid}, '60{i:04d}', 'Stock{i}', 'SSE', 'stock', "
                "'2000-01-01', TRUE)"
            )
        self.client.commit()

        # Act
        sids = self.repo.list_all()

        # Assert
        assert len(sids) == 3
        assert 100000001 in sids
        assert 100000002 in sids

    def test_get_symbol(self) -> None:
        """Test getting symbol by sid."""
        # Arrange
        self.client.execute("""
            INSERT INTO security
            (sid, symbol, name, exchange, asset_class, list_date)
            VALUES (100000001, '600000', 'Test', 'SSE', 'stock', '1999-11-10')
        """)
        self.client.commit()

        # Act
        symbol = self.repo.get_symbol(100000001)

        # Assert
        assert symbol == "600000"

    def test_get_src_code(self) -> None:
        """Test getting src_code by sid."""
        # Arrange
        self.client.execute("""
            INSERT INTO security
            (sid, symbol, name, exchange, asset_class, list_date)
            VALUES (100000001, '600000', 'Test', 'SSE', 'stock', '1999-11-10')
        """)
        self.client.execute("""
            INSERT INTO security_mapping
            (sid, source, src_code, effective_from)
            VALUES (100000001, 'tushare', '600000.SH', '1999-11-10')
        """)
        self.client.commit()

        # Act
        src_code = self.repo.get_src_code(100000001, "tushare")

        # Assert
        assert src_code == "600000.SH"

    def test_register_allocates_sid(self) -> None:
        """Test register allocates new SID."""
        # Act
        sid = self.repo.register(
            src_code="600001.SH",
            symbol="600001",
            name="Test Stock",
            exchange="SSE",
            asset_class="stock",
            list_date="2000-01-01",
        )

        # Assert
        assert sid == 100000001  # First stock SID (starts at STOCK_MIN + 1)

        # Verify in database
        security = self.repo.get_by_sid(sid)
        assert security is not None
        assert security["symbol"] == "600001"

    def teardown_method(self) -> None:
        """Clean up after test."""
        # No cleanup needed for in-memory database
        pass
