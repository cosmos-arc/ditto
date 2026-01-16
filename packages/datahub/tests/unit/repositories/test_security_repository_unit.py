"""Tests for SecurityRepository."""

import polars as pl
import pytest
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
            VALUES (1000001, '600000', 'Bank', 'SSE', 'stock', '2000-01-01')
        """)
        self.client.execute("""
            INSERT INTO security_mapping
            (sid, source, src_code, effective_from)
            VALUES (1000001, 'tushare', '600000.SH', '2000-01-01')
        """)
        self.client.commit()

        # Act
        result = self.repo.get(sids=[1000001])

        # Assert
        assert len(result) == 1
        assert result["sid"][0] == 1000001
        assert result["symbol"][0] == "600000"

    def test_resolve_identifier_with_src_code(self) -> None:
        """Test resolve_identifier with src_code."""
        # Arrange
        self.client.execute("""
            INSERT INTO security
            (sid, symbol, name, exchange, asset_class, list_date)
            VALUES (1000001, '600000', 'Bank', 'SSE', 'stock', '2000-01-01')
        """)
        self.client.execute("""
            INSERT INTO security_mapping
            (sid, source, src_code, effective_from)
            VALUES (1000001, 'tushare', '600000.SH', '2000-01-01')
        """)
        self.client.commit()

        # Act
        sid = self.repo.resolve_identifier("600000.SH", "tushare")

        # Assert
        assert sid == 1000001

    def test_resolve_identifier_with_symbol(self) -> None:
        """Test resolve_identifier with symbol."""
        # Arrange
        self.client.execute("""
            INSERT INTO security
            (sid, symbol, name, exchange, asset_class, list_date)
            VALUES (1000001, '600000', 'Bank', 'SSE', 'stock', '2000-01-01')
        """)
        self.client.execute("""
            INSERT INTO security_mapping
            (sid, source, src_code, effective_from)
            VALUES (1000001, 'tushare', '600000.SH', '2000-01-01')
        """)
        self.client.commit()

        # Act
        sid = self.repo.resolve_identifier("600000", "tushare")

        # Assert
        assert sid == 1000001

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
            sid = 1000001 + i
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
        assert result["600000.SH"] == 1000001
        assert result["600001.SH"] == 1000002
        assert "600003.SH" not in result  # Not found

    def test_get_by_sid(self) -> None:
        """Test getting security by sid."""
        # Arrange
        self.client.execute("""
            INSERT INTO security
            (sid, symbol, name, exchange, asset_class, list_date)
            VALUES (1000001, '600000', 'Test Bank', 'SSE', 'stock', '1999-11-10')
        """)
        self.client.commit()

        # Act
        result = self.repo.get_by_sid(1000001)

        # Assert
        assert result is not None
        assert result["sid"] == 1000001
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
            sid = 1000001 + i
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
        assert 1000001 in sids
        assert 1000002 in sids

    def test_get_symbol(self) -> None:
        """Test getting symbol by sid."""
        # Arrange
        self.client.execute("""
            INSERT INTO security
            (sid, symbol, name, exchange, asset_class, list_date)
            VALUES (1000001, '600000', 'Test', 'SSE', 'stock', '1999-11-10')
        """)
        self.client.commit()

        # Act
        symbol = self.repo.get_symbol(1000001)

        # Assert
        assert symbol == "600000"

    def test_get_src_code(self) -> None:
        """Test getting src_code by sid."""
        # Arrange
        self.client.execute("""
            INSERT INTO security
            (sid, symbol, name, exchange, asset_class, list_date)
            VALUES (1000001, '600000', 'Test', 'SSE', 'stock', '1999-11-10')
        """)
        self.client.execute("""
            INSERT INTO security_mapping
            (sid, source, src_code, effective_from)
            VALUES (1000001, 'tushare', '600000.SH', '1999-11-10')
        """)
        self.client.commit()

        # Act
        src_code = self.repo.get_src_code(1000001, "tushare")

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
        assert sid == 1000001  # First stock SID (starts at STOCK_MIN + 1)

        # Verify in database
        security = self.repo.get_by_sid(sid)
        assert security is not None
        assert security["symbol"] == "600001"

    def test_register_batch_registers_multiple_securities(self) -> None:
        """Test register_batch registers multiple securities from DataFrame."""
        # Arrange
        df = pl.DataFrame(
            {
                "src_code": ["600001.SH", "600002.SH", "600003.SH"],
                "symbol": ["600001", "600002", "600003"],
                "name": ["Stock1", "Stock2", "Stock3"],
                "exchange": ["SSE", "SSE", "SSE"],
                "list_date": ["2000-01-01", "2000-01-02", "2000-01-03"],
            }
        )

        # Act
        file_path, checksum = self.repo.register_batch(
            df=df,
            source="tushare",
            asset_class="stock",
            src_code_col="src_code",
        )

        # Assert
        assert isinstance(file_path, str)
        assert isinstance(checksum, str)
        assert len(checksum) == 32  # MD5 hash length

        # Verify all securities were registered
        assert self.repo.get_by_sid(1000001) is not None
        assert self.repo.get_by_sid(1000002) is not None
        assert self.repo.get_by_sid(1000003) is not None

    def test_register_batch_handles_existing_securities(self) -> None:
        """Test register_batch skips existing securities."""
        # Arrange
        # Register first security
        df1 = pl.DataFrame(
            {
                "src_code": ["600001.SH"],
                "symbol": ["600001"],
                "name": ["Stock1"],
                "exchange": ["SSE"],
                "list_date": ["2000-01-01"],
            }
        )
        self.repo.register_batch(
            df=df1, source="tushare", asset_class="stock", src_code_col="src_code"
        )

        # Try to register again (should skip existing)
        df2 = pl.DataFrame(
            {
                "src_code": ["600001.SH", "600002.SH"],
                "symbol": ["600001", "600002"],
                "name": ["Stock1", "Stock2"],
                "exchange": ["SSE", "SSE"],
                "list_date": ["2000-01-01", "2000-01-02"],
            }
        )

        # Act
        _file_path, _checksum = self.repo.register_batch(
            df=df2, source="tushare", asset_class="stock", src_code_col="src_code"
        )

        # Assert - should only register the new one
        assert self.repo.get_by_sid(1000001) is not None  # Existing
        assert self.repo.get_by_sid(1000002) is not None  # New
        # Third security should not exist (only 2 registered)
        assert self.repo.get_by_sid(1000003) is None

    def test_resolve_or_create_batch_with_empty_dataframe(self) -> None:
        """Test resolve_or_create_batch with empty DataFrame."""
        # Arrange
        df = pl.DataFrame(
            {
                "ts_code": [],
                "symbol": [],
                "name": [],
                "exchange": [],
                "list_date": [],
            }
        )

        # Act
        result = self.repo.resolve_or_create_batch(
            df=df,
            source="tushare",
            asset_class="stock",
            src_code_col="ts_code",
        )

        # Assert
        assert result == {}

    def test_resolve_or_create_batch_with_all_existing(self) -> None:
        """Test resolve_or_create_batch when all securities already exist."""
        # Arrange
        # Register existing securities
        df_existing = pl.DataFrame(
            {
                "src_code": ["600001.SH", "600002.SH"],
                "symbol": ["600001", "600002"],
                "name": ["Stock1", "Stock2"],
                "exchange": ["SSE", "SSE"],
                "list_date": ["2000-01-01", "2000-01-02"],
            }
        )
        self.repo.register_batch(
            df=df_existing,
            source="tushare",
            asset_class="stock",
            src_code_col="src_code",
        )

        # Try to resolve same securities
        df = pl.DataFrame(
            {
                "ts_code": ["600001.SH", "600002.SH"],
                "symbol": ["600001", "600002"],
                "name": ["Stock1", "Stock2"],
                "exchange": ["SSE", "SSE"],
                "list_date": ["2000-01-01", "2000-01-02"],
            }
        )

        # Act
        result = self.repo.resolve_or_create_batch(
            df=df,
            source="tushare",
            asset_class="stock",
            src_code_col="ts_code",
        )

        # Assert
        assert len(result) == 2
        assert result["600001.SH"] == 1000001
        assert result["600002.SH"] == 1000002

    def test_resolve_or_create_batch_with_all_new(self) -> None:
        """Test resolve_or_create_batch when all securities are new."""
        # Arrange
        df = pl.DataFrame(
            {
                "ts_code": ["600001.SH", "600002.SH", "600003.SH"],
                "symbol": ["600001", "600002", "600003"],
                "name": ["Stock1", "Stock2", "Stock3"],
                "exchange": ["SSE", "SSE", "SSE"],
                "list_date": ["2000-01-01", "2000-01-02", "2000-01-03"],
            }
        )

        # Act
        result = self.repo.resolve_or_create_batch(
            df=df,
            source="tushare",
            asset_class="stock",
            src_code_col="ts_code",
        )

        # Assert
        assert len(result) == 3
        assert result["600001.SH"] == 1000001
        assert result["600002.SH"] == 1000002
        assert result["600003.SH"] == 1000003

        # Verify securities were created
        assert self.repo.get_by_sid(1000001) is not None
        assert self.repo.get_by_sid(1000002) is not None
        assert self.repo.get_by_sid(1000003) is not None

    def test_resolve_or_create_batch_mixed_existing_and_new(self) -> None:
        """Test resolve_or_create_batch with mixed existing and new securities."""
        # Arrange
        # Register one existing security
        df_existing = pl.DataFrame(
            {
                "src_code": ["600001.SH"],
                "symbol": ["600001"],
                "name": ["Stock1"],
                "exchange": ["SSE"],
                "list_date": ["2000-01-01"],
            }
        )
        self.repo.register_batch(
            df=df_existing,
            source="tushare",
            asset_class="stock",
            src_code_col="src_code",
        )

        # Mix existing and new
        df = pl.DataFrame(
            {
                "ts_code": ["600001.SH", "600002.SH", "600003.SH"],
                "symbol": ["600001", "600002", "600003"],
                "name": ["Stock1", "Stock2", "Stock3"],
                "exchange": ["SSE", "SSE", "SSE"],
                "list_date": ["2000-01-01", "2000-01-02", "2000-01-03"],
            }
        )

        # Act
        result = self.repo.resolve_or_create_batch(
            df=df,
            source="tushare",
            asset_class="stock",
            src_code_col="ts_code",
        )

        # Assert
        assert len(result) == 3
        assert result["600001.SH"] == 1000001  # Existing
        assert result["600002.SH"] == 1000002  # New
        assert result["600003.SH"] == 1000003  # New

    def test_resolve_or_create_batch_missing_required_columns(self) -> None:
        """Test resolve_or_create_batch raises error for missing columns."""
        # Arrange
        df = pl.DataFrame(
            {
                "ts_code": ["600001.SH"],
                "symbol": ["600001"],
                # Missing: name, exchange, list_date
            }
        )

        # Act & Assert
        expected_match = "name|exchange|list_date"
        with pytest.raises(KeyError, match=expected_match):
            self.repo.resolve_or_create_batch(
                df=df,
                source="tushare",
                asset_class="stock",
                src_code_col="ts_code",
            )

    def test_enrich_dataframe_with_sid(self) -> None:
        """Test enrich_dataframe_with_sid adds sid and source columns."""
        # Arrange
        df = pl.DataFrame(
            {
                "ts_code": ["600001.SH", "600002.SH"],
                "symbol": ["600001", "600002"],
                "name": ["Stock1", "Stock2"],
                "exchange": ["SSE", "SSE"],
                "list_date": ["2000-01-01", "2000-01-02"],
                "other_col": ["a", "b"],  # Additional column should be preserved
            }
        )

        # Act
        result = self.repo.enrich_dataframe_with_sid(
            df=df,
            source="tushare",
            asset_class="stock",
            src_code_col="ts_code",
        )

        # Assert
        assert "sid" in result.columns
        assert "source" in result.columns
        assert result["sid"].to_list() == [1000001, 1000002]
        assert result["source"].to_list() == ["tushare", "tushare"]
        assert "other_col" in result.columns  # Original columns preserved
        assert result["other_col"].to_list() == ["a", "b"]

    def test_enrich_dataframe_with_sid_with_existing_securities(self) -> None:
        """Test enrich_dataframe_with_sid with existing securities."""
        # Arrange
        # Register existing securities
        df_existing = pl.DataFrame(
            {
                "src_code": ["600001.SH"],
                "symbol": ["600001"],
                "name": ["Stock1"],
                "exchange": ["SSE"],
                "list_date": ["2000-01-01"],
            }
        )
        self.repo.register_batch(
            df=df_existing,
            source="tushare",
            asset_class="stock",
            src_code_col="src_code",
        )

        # Enrich DataFrame with existing and new
        df = pl.DataFrame(
            {
                "ts_code": ["600001.SH", "600002.SH"],
                "symbol": ["600001", "600002"],
                "name": ["Stock1", "Stock2"],
                "exchange": ["SSE", "SSE"],
                "list_date": ["2000-01-01", "2000-01-02"],
            }
        )

        # Act
        result = self.repo.enrich_dataframe_with_sid(
            df=df,
            source="tushare",
            asset_class="stock",
            src_code_col="ts_code",
        )

        # Assert
        assert result["sid"].to_list() == [1000001, 1000002]
        assert result["source"].to_list() == ["tushare", "tushare"]

    def test_enrich_dataframe_with_sid_with_etf(self) -> None:
        """Test enrich_dataframe_with_sid with ETF asset class."""
        # Arrange
        df = pl.DataFrame(
            {
                "ts_code": ["510300.SH"],
                "symbol": "510300",
                "name": "ETF300",
                "exchange": "SSE",
                "list_date": "2012-01-01",
            }
        )

        # Act
        result = self.repo.enrich_dataframe_with_sid(
            df=df,
            source="tushare",
            asset_class="etf",
            src_code_col="ts_code",
        )

        # Assert
        # ETF SIDs start from 2000001
        assert result["sid"][0] == 2000001
        assert result["source"][0] == "tushare"

    def teardown_method(self) -> None:
        """Clean up after test."""
        # No cleanup needed for in-memory database
        pass
