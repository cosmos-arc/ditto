"""Tests for BarsRepository."""

import random
import time
from dataclasses import FrozenInstanceError
from datetime import date, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

import polars as pl
import pytest
from ditto_datahub.dq.engine import DQEngine
from ditto_datahub.repositories import AdjType, BarsQuery, BarsRepository
from ditto_datahub.repositories.bars.repository import _ResolvedQuery
from ditto_datahub.stores.adj_factor_store import AdjFactorStore
from ditto_datahub.stores.bars_store import BarsStore
from ditto_datahub.stores.quarantine_store import QuarantineStore
from ditto_datahub.stores.security_store import SecurityStore
from ditto_datahub.stores.sqlite_client import SQLiteClient
from ditto_datahub.stores.stock_status_store import StockStatusStore  # B.3
from ditto_foundation import SQLitePool
from ditto_foundation.concurrency import FileLockManager
from pytest_mock import MockerFixture


class TestBarsQuery:
    """Tests for BarsQuery dataclass."""

    def test_bars_query_creation_with_default_values(self) -> None:
        """Test BarsQuery can be created with default values."""
        # Act
        query = BarsQuery()

        # Assert
        assert query.sids is None
        assert query.src_codes is None
        assert query.symbols is None
        assert query.start is None
        assert query.end is None
        assert query.adj == AdjType.NONE
        assert query.asof is None
        assert query.asset_class is None
        assert query.with_symbol is False
        assert query.with_status is False
        assert query.market_wide is False
        assert query.raw is False

    def test_bars_query_creation_with_values(self) -> None:
        """Test BarsQuery can be created with specific values."""
        # Act
        query = BarsQuery(
            sids=[1, 2, 3],
            src_codes=["600000.SH", "600001.SH"],
            symbols=["600000", "600001"],
            start="2024-01-01",
            end="2024-01-31",
            adj=AdjType.QFQ,
            asof="2024-01-15",
            asset_class="stock",
            with_symbol=True,
            with_status=True,
            market_wide=False,
            raw=True,
        )

        # Assert
        assert query.sids == [1, 2, 3]
        assert query.src_codes == ["600000.SH", "600001.SH"]
        assert query.symbols == ["600000", "600001"]
        assert query.start == "2024-01-01"
        assert query.end == "2024-01-31"
        assert query.adj == AdjType.QFQ
        assert query.asof == "2024-01-15"
        assert query.asset_class == "stock"
        assert query.with_symbol is True
        assert query.with_status is True
        assert query.market_wide is False
        assert query.raw is True

    def test_bars_query_with_index_asset_class(self) -> None:
        """Test BarsQuery with index asset class."""
        # Act
        query = BarsQuery(asset_class="index")

        # Assert
        assert query.asset_class == "index"

    def test_bars_query_is_frozen(self) -> None:
        """Test BarsQuery is immutable (frozen=True)."""
        # Arrange
        query = BarsQuery(sids=[1, 2, 3])

        # Act & Assert: Frozen dataclass raises FrozenInstanceError
        with pytest.raises(FrozenInstanceError):
            query.sids = [4, 5, 6]

    def test_bars_query_with_etf_asset_class(self) -> None:
        """Test BarsQuery with ETF asset class."""
        # Act
        query = BarsQuery(
            sids=[2000001],
            asset_class="etf",
            adj=AdjType.HFQ,
        )

        # Assert
        assert query.asset_class == "etf"
        assert query.adj == AdjType.HFQ

    def test_bars_query_market_wide_mode(self) -> None:
        """Test BarsQuery with market_wide mode."""
        # Act
        query = BarsQuery(
            market_wide=True,
            asset_class="stock",
            start="2024-01-01",
            end="2024-01-31",
        )

        # Assert
        assert query.market_wide is True
        assert query.asset_class == "stock"

    def test_bars_query_partial_parameters(self) -> None:
        """Test BarsQuery with partial parameters."""
        # Act
        query = BarsQuery(
            sids=[1000001],
            start="2024-01-01",
        )

        # Assert
        assert query.sids == [1000001]
        assert query.start == "2024-01-01"
        assert query.end is None  # Default
        assert query.adj == AdjType.NONE  # Default
        assert query.with_symbol is False  # Default


class TestResolvedQuery:
    """Tests for _ResolvedQuery dataclass."""

    def test_resolved_query_creation_with_all_fields(self) -> None:
        """Test _ResolvedQuery can be created with all fields."""
        # Act
        resolved = _ResolvedQuery(
            sids=[1, 2, 3],
            start=date(2024, 1, 1),
            end=date(2024, 1, 31),
            asof=date(2024, 1, 15),
            asset_class="stock",
        )

        # Assert
        assert resolved.sids == [1, 2, 3]
        assert resolved.start == date(2024, 1, 1)
        assert resolved.end == date(2024, 1, 31)
        assert resolved.asof == date(2024, 1, 15)
        assert resolved.asset_class == "stock"

    def test_resolved_query_with_none_dates(self) -> None:
        """Test _ResolvedQuery with None date values."""
        # Act
        resolved = _ResolvedQuery(
            sids=[1000001],
            start=None,
            end=None,
            asof=None,
            asset_class=None,
        )

        # Assert
        assert resolved.sids == [1000001]
        assert resolved.start is None
        assert resolved.end is None
        assert resolved.asof is None
        assert resolved.asset_class is None

    def test_resolved_query_with_etf_asset_class(self) -> None:
        """Test _ResolvedQuery with ETF asset class."""
        # Act
        resolved = _ResolvedQuery(
            sids=[2000001, 2000002],
            start=date(2024, 1, 1),
            end=date(2024, 1, 31),
            asof=None,
            asset_class="etf",
        )

        # Assert
        assert resolved.sids == [2000001, 2000002]
        assert resolved.asset_class == "etf"

    def test_resolved_query_with_index_asset_class(self) -> None:
        """Test _ResolvedQuery with index asset class."""
        # Act
        resolved = _ResolvedQuery(
            sids=[3000001],
            start=date(2024, 1, 1),
            end=date(2024, 1, 31),
            asof=None,
            asset_class="index",
        )

        # Assert
        assert resolved.sids == [3000001]
        assert resolved.asset_class == "index"

    def test_resolved_query_is_frozen(self) -> None:
        """Test _ResolvedQuery is immutable (frozen=True)."""
        # Arrange
        resolved = _ResolvedQuery(
            sids=[1, 2, 3],
            start=date(2024, 1, 1),
            end=date(2024, 1, 31),
            asof=None,
            asset_class="stock",
        )

        # Act & Assert: Frozen dataclass raises FrozenInstanceError
        with pytest.raises(FrozenInstanceError):
            resolved.sids = [4, 5, 6]

    def test_resolved_query_has_slots(self) -> None:
        """Test _ResolvedQuery uses __slots__ (slots=True)."""
        # Arrange & Act
        resolved = _ResolvedQuery(
            sids=[1],
            start=date(2024, 1, 1),
            end=None,
            asof=None,
            asset_class=None,
        )

        # Assert: __slots__ prevents __dict__ creation
        assert not hasattr(resolved, "__dict__")

    def test_resolved_query_with_single_sid(self) -> None:
        """Test _ResolvedQuery with single SID."""
        # Act
        resolved = _ResolvedQuery(
            sids=[1000001],
            start=date(2024, 1, 1),
            end=date(2024, 1, 31),
            asof=None,
            asset_class="stock",
        )

        # Assert
        assert resolved.sids == [1000001]
        assert len(resolved.sids) == 1

    def test_resolved_query_empty_sid_list(self) -> None:
        """Test _ResolvedQuery with empty SID list."""
        # Act
        resolved = _ResolvedQuery(
            sids=[],
            start=date(2024, 1, 1),
            end=date(2024, 1, 31),
            asof=None,
            asset_class="stock",
        )

        # Assert
        assert resolved.sids == []
        assert len(resolved.sids) == 0

    def test_resolved_query_with_asof_date(self) -> None:
        """Test _ResolvedQuery with asof date for PIT-safe queries."""
        # Act
        resolved = _ResolvedQuery(
            sids=[1, 2, 3],
            start=date(2024, 1, 1),
            end=date(2024, 1, 31),
            asof=date(2024, 1, 15),
            asset_class="stock",
        )

        # Assert
        assert resolved.asof == date(2024, 1, 15)


@pytest.mark.pit
class TestBarsRepository:
    """
    Tests for BarsRepository.

    PIT (Pipeline Integration Tests) - tests complete data ingestion flow.
    These tests require more resources and time than unit tests.
    """

    def setup_method(self) -> None:
        """Set up test environment."""
        self.temp_dir = TemporaryDirectory()
        data_root = Path(self.temp_dir.name)

        self.pool = SQLitePool(":memory:")
        self.pool.init_schema()
        self.client = SQLiteClient(self.pool)

        self.bars_store = BarsStore(data_root)
        self.adj_factor_store = AdjFactorStore(data_root)
        self.security_store = SecurityStore(self.client)
        self.stock_status_store = StockStatusStore(data_root)  # B.3
        self.dq_engine = DQEngine()
        self.file_lock_manager = FileLockManager(data_root / "locks")
        self.quarantine_store = QuarantineStore(data_root / "quarantine.db")

        self.repo = BarsRepository(
            self.bars_store,
            self.adj_factor_store,
            self.security_store,
            self.stock_status_store,  # B.3
            self.dq_engine,
            self.file_lock_manager,
            self.quarantine_store,
        )

        # Insert test security
        self.client.execute("""
            INSERT INTO security
            (sid, symbol, name, exchange, asset_class, list_date)
            VALUES (1000001, '600000', 'Test', 'SSE', 'stock', '2000-01-01')
        """)
        self.client.execute("""
            INSERT INTO security_mapping
            (sid, source, src_code, effective_from)
            VALUES (1000001, 'tushare', '600000.SH', '2000-01-01')
        """)
        self.client.commit()

    def teardown_method(self) -> None:
        """Clean up test environment."""
        # Close SQLite connection before cleanup (Windows file lock)
        if hasattr(self, "quarantine_store"):
            self.quarantine_store.close()
        self.temp_dir.cleanup()

    def test_get_returns_empty_dataframe_for_no_data(self) -> None:
        """Test get returns empty DataFrame when no data exists."""
        result = self.repo.get(
            query=BarsQuery(
                sids=[1000001],
                start="2024-01-01",
                end="2024-01-31",
            )
        )

        assert isinstance(result, pl.DataFrame)
        assert result.is_empty()

    def test_get_returns_bars_data(self) -> None:
        """Test get returns bars data."""
        # Arrange
        test_df = pl.DataFrame(
            {
                "sid": [1000001, 1000001],
                "trade_date": [date(2024, 1, 2), date(2024, 1, 3)],
                "open": [10.0, 11.0],
                "high": [12.0, 13.0],
                "low": [9.0, 10.0],
                "close": [11.0, 12.0],
                "volume": [1000, 2000],
            }
        )
        self.bars_store.write("stock_daily", test_df, 2024)

        # Act
        result = self.repo.get(
            query=BarsQuery(
                sids=[1000001],
                start="2024-01-01",
                end="2024-01-31",
            )
        )

        # Assert
        assert len(result) == 2
        # Check values exist (order may vary due to sorting)
        assert set(result["close"].to_list()) == {11.0, 12.0}

    def test_get_with_symbol_enrichment(self) -> None:
        """Test get enriches with symbol column."""
        # Arrange
        test_df = pl.DataFrame(
            {
                "sid": [1000001],
                "trade_date": [date(2024, 1, 2)],
                "open": [10.0],
                "high": [12.0],
                "low": [9.0],
                "close": [11.0],
                "volume": [1000],
            }
        )
        self.bars_store.write("stock_daily", test_df, 2024)

        # Act
        result = self.repo.get(
            query=BarsQuery(
                sids=[1000001],
                start="2024-01-01",
                end="2024-01-31",
                with_symbol=True,
            )
        )

        # Assert
        assert "symbol" in result.columns
        assert result["symbol"][0] == "600000"


class TestPITSafeAdjustment:
    """Tests for PIT-safe (Point-in-Time) adjustment calculation."""

    def setup_method(self) -> None:
        """Set up test environment."""
        self.temp_dir = TemporaryDirectory()
        data_root = Path(self.temp_dir.name)

        self.pool = SQLitePool(":memory:")
        self.pool.init_schema()
        self.client = SQLiteClient(self.pool)

        self.bars_store = BarsStore(data_root)
        self.adj_factor_store = AdjFactorStore(data_root)
        self.security_store = SecurityStore(self.client)
        self.stock_status_store = StockStatusStore(data_root)  # B.3
        self.dq_engine = DQEngine()
        self.file_lock_manager = FileLockManager(data_root / "locks")
        self.quarantine_store = QuarantineStore(data_root / "quarantine.db")

        self.repo = BarsRepository(
            self.bars_store,
            self.adj_factor_store,
            self.security_store,
            self.stock_status_store,  # B.3
            self.dq_engine,
            self.file_lock_manager,
            self.quarantine_store,
        )

        # Insert test security
        self.client.execute("""
            INSERT INTO security
            (sid, symbol, name, exchange, asset_class, list_date)
            VALUES (1000001, '600000', 'Test Stock', 'SSE', 'stock', '2000-01-01')
        """)
        self.client.commit()

    def teardown_method(self) -> None:
        """Clean up test environment."""
        # Close SQLite connection before cleanup (Windows file lock)
        if hasattr(self, "quarantine_store"):
            self.quarantine_store.close()
        self.temp_dir.cleanup()

    def test_qfq_uses_knowledge_date_not_trade_date(self) -> None:
        """
        Test that QFQ adjustment uses knowledge_date for PIT safety.

        Scenario:
        - Trade date: 2024-01-03
        - Adj factor published on: 2024-01-04 (T+1)
        - Query asof: 2024-01-03

        Expected behavior:
        - When asof=2024-01-03, the adj factor from 2024-01-03 should NOT be used
          because it wasn't published until 2024-01-04 (knowledge_date).
        - PIT-safe: Only use adj factors where knowledge_date <= asof_date.
        """
        # Arrange: Write bars data
        bars_df = pl.DataFrame(
            {
                "sid": [1000001, 1000001, 1000001],
                "trade_date": [
                    date(2024, 1, 2),
                    date(2024, 1, 3),
                    date(2024, 1, 4),
                ],
                "open": [10.0, 10.0, 10.0],
                "high": [12.0, 12.0, 12.0],
                "low": [9.0, 9.0, 9.0],
                "close": [11.0, 11.0, 11.0],
                "volume": [1000, 2000, 3000],
            }
        )
        self.bars_store.write("stock_daily", bars_df, 2024)

        # Write adj_factor data with knowledge_date (T+1 publication)
        # The factor on 2024-01-03 is published on 2024-01-04 (knowledge_date)
        adj_df = pl.DataFrame(
            {
                "sid": [1000001, 1000001, 1000001],
                "trade_date": [
                    date(2024, 1, 2),
                    date(2024, 1, 3),
                    date(2024, 1, 4),
                ],
                "adj_factor": [1.0, 0.95, 0.95],
                "knowledge_date": [
                    date(2024, 1, 2),  # Published same day
                    date(2024, 1, 4),  # T+1 (2024-01-03 factor available 2024-01-04)
                    date(2024, 1, 5),  # Published T+1
                ],
            }
        )
        self.adj_factor_store.write("adj_factor", adj_df, 2024)

        # Act: Get QFQ adjusted data asof 2024-01-03
        # PIT-safe: Should only use adj factors with knowledge_date <= 2024-01-03
        result = self.repo.get(
            query=BarsQuery(
                sids=[1000001],
                start="2024-01-02",
                end="2024-01-04",
                adj=AdjType.QFQ,
                asof="2024-01-03",  # Query point
            )
        )

        # Assert: PIT-safe behavior
        # The 0.95 factor from 2024-01-03 has knowledge_date=2024-01-04
        # So when asof=2024-01-03, this factor should NOT be used
        result_sorted = result.sort("trade_date")
        assert len(result_sorted) == 3

        # With PIT safety, latest_factor should be 1.0 (not 0.95)
        # because 0.95 factor's knowledge_date (2024-01-04) > asof (2024-01-03)
        # So all prices should be original (no adjustment)
        assert abs(result_sorted["close"][0] - 11.00) < 0.01  # 2024-01-02
        assert abs(result_sorted["close"][1] - 11.00) < 0.01  # 2024-01-03
        assert abs(result_sorted["close"][2] - 11.00) < 0.01  # 2024-01-04

    def test_qfq_with_knowledge_date_uses_later_factors(self) -> None:
        """
        Test QFQ with knowledge_date uses later factors when asof allows.

        Scenario:
        - Same data as above
        - Query asof: 2024-01-05

        Expected behavior:
        - When asof=2024-01-05, all adj factors should be available
          (all knowledge_date <= 2024-01-05)
        - latest_factor should be 0.95
        """
        # Arrange: Write bars data
        bars_df = pl.DataFrame(
            {
                "sid": [1000001, 1000001, 1000001],
                "trade_date": [
                    date(2024, 1, 2),
                    date(2024, 1, 3),
                    date(2024, 1, 4),
                ],
                "open": [10.0, 10.0, 10.0],
                "high": [12.0, 12.0, 12.0],
                "low": [9.0, 9.0, 9.0],
                "close": [11.0, 11.0, 11.0],
                "volume": [1000, 2000, 3000],
            }
        )
        self.bars_store.write("stock_daily", bars_df, 2024)

        # Write adj_factor data with knowledge_date (T+1 publication)
        adj_df = pl.DataFrame(
            {
                "sid": [1000001, 1000001, 1000001],
                "trade_date": [
                    date(2024, 1, 2),
                    date(2024, 1, 3),
                    date(2024, 1, 4),
                ],
                "adj_factor": [1.0, 0.95, 0.95],
                "knowledge_date": [
                    date(2024, 1, 2),
                    date(2024, 1, 4),
                    date(2024, 1, 5),
                ],
            }
        )
        self.adj_factor_store.write("adj_factor", adj_df, 2024)

        # Act: Get QFQ adjusted data asof 2024-01-05
        # All factors should be available (all knowledge_date <= 2024-01-05)
        result = self.repo.get(
            query=BarsQuery(
                sids=[1000001],
                start="2024-01-02",
                end="2024-01-04",
                adj=AdjType.QFQ,
                asof="2024-01-05",  # Later query point
            )
        )

        # Assert: Should use latest_factor = 0.95
        result_sorted = result.sort("trade_date")
        assert len(result_sorted) == 3
        # QFQ: adj_price = orig_price * cur_factor / latest_factor
        # latest_factor = 0.95
        assert (
            abs(result_sorted["close"][0] - 11.579) < 0.01
        )  # 2024-01-02: 11.0 * 1.0 / 0.95
        assert (
            abs(result_sorted["close"][1] - 11.00) < 0.01
        )  # 2024-01-03: 11.0 * 0.95 / 0.95
        assert (
            abs(result_sorted["close"][2] - 11.00) < 0.01
        )  # 2024-01-04: 11.0 * 0.95 / 0.95


class TestQFQAdjustment:
    """Tests for QFQ (前复权) adjustment."""

    def setup_method(self) -> None:
        """Set up test environment."""
        self.temp_dir = TemporaryDirectory()
        data_root = Path(self.temp_dir.name)

        self.pool = SQLitePool(":memory:")
        self.pool.init_schema()
        self.client = SQLiteClient(self.pool)

        self.bars_store = BarsStore(data_root)
        self.adj_factor_store = AdjFactorStore(data_root)
        self.security_store = SecurityStore(self.client)
        self.stock_status_store = StockStatusStore(data_root)  # B.3
        self.dq_engine = DQEngine()
        self.file_lock_manager = FileLockManager(data_root / "locks")
        self.quarantine_store = QuarantineStore(data_root / "quarantine.db")

        self.repo = BarsRepository(
            self.bars_store,
            self.adj_factor_store,
            self.security_store,
            self.stock_status_store,  # B.3
            self.dq_engine,
            self.file_lock_manager,
            self.quarantine_store,
        )

        # Insert test security
        self.client.execute("""
            INSERT INTO security
            (sid, symbol, name, exchange, asset_class, list_date)
            VALUES (1000001, '600000', 'Test Stock', 'SSE', 'stock', '2000-01-01')
        """)
        self.client.commit()

    def teardown_method(self) -> None:
        """Clean up test environment."""
        # Close SQLite connection before cleanup (Windows file lock)
        if hasattr(self, "quarantine_store"):
            self.quarantine_store.close()
        self.temp_dir.cleanup()

    def test_qfq_uses_latest_adj_factor(self) -> None:
        """Test that QFQ adjustment uses the latest adj_factor correctly."""
        # Arrange: Write bars data with consistent prices
        bars_df = pl.DataFrame(
            {
                "sid": [1000001, 1000001, 1000001],
                "trade_date": [date(2024, 1, 2), date(2024, 1, 3), date(2024, 1, 4)],
                "open": [10.0, 10.0, 10.0],
                "high": [12.0, 12.0, 12.0],
                "low": [9.0, 9.0, 9.0],
                "close": [11.0, 11.0, 11.0],
                "volume": [1000, 2000, 3000],
            }
        )
        self.bars_store.write("stock_daily", bars_df, 2024)

        # Write adj_factor data: 0.95 on 2024-01-03 and later
        adj_df = pl.DataFrame(
            {
                "sid": [1000001, 1000001, 1000001],
                "trade_date": [date(2024, 1, 2), date(2024, 1, 3), date(2024, 1, 4)],
                "adj_factor": [1.0, 0.95, 0.95],
            }
        )
        self.adj_factor_store.write("adj_factor", adj_df, 2024)

        # Act: Get QFQ adjusted data
        result = self.repo.get(
            query=BarsQuery(
                sids=[1000001],
                start="2024-01-02",
                end="2024-01-04",
                adj=AdjType.QFQ,
            )
        )

        # Assert: QFQ should adjust all prices to the latest reference point
        # Tushare QFQ: adj_price = orig_price * cur_factor / latest_factor
        # latest_factor = 0.95 (the last factor in the period)
        # 2024-01-02: 11.0 * 1.0 / 0.95 = 11.579
        # 2024-01-03: 11.0 * 0.95 / 0.95 = 11.0
        # 2024-01-04: 11.0 * 0.95 / 0.95 = 11.0
        result_sorted = result.sort("trade_date")
        assert len(result_sorted) == 3
        assert abs(result_sorted["close"][0] - 11.579) < 0.01  # 2024-01-02
        assert abs(result_sorted["close"][1] - 11.00) < 0.01  # 2024-01-03
        assert abs(result_sorted["close"][2] - 11.00) < 0.01  # 2024-01-04

    def test_qfq_with_missing_adj_factor_uses_original_price(self) -> None:
        """Test QFQ adjustment handles missing adj_factor gracefully."""
        # Arrange: Write bars data
        bars_df = pl.DataFrame(
            {
                "sid": [1000001, 1000001],
                "trade_date": [date(2024, 1, 2), date(2024, 1, 3)],
                "open": [10.0, 11.0],
                "high": [12.0, 13.0],
                "low": [9.0, 10.0],
                "close": [11.0, 12.0],
                "volume": [1000, 2000],
            }
        )
        self.bars_store.write("stock_daily", bars_df, 2024)

        # Write adj_factor data only for 2024-01-03 (missing for 2024-01-02)
        adj_df = pl.DataFrame(
            {
                "sid": [1000001],
                "trade_date": [date(2024, 1, 3)],
                "adj_factor": [0.95],
            }
        )
        self.adj_factor_store.write("adj_factor", adj_df, 2024)

        # Act: Get QFQ adjusted data
        result = self.repo.get(
            query=BarsQuery(
                sids=[1000001],
                start="2024-01-02",
                end="2024-01-03",
                adj=AdjType.QFQ,
            )
        )

        # Assert: QFQ uses latest_factor (0.95) for all dates
        # Tushare QFQ: adj_price = orig_price * cur_factor / latest_factor
        # 2024-01-02: 11.0 * 1.0 (coalesced null adj_factor) / 0.95 = 11.579
        # 2024-01-03: 12.0 * 0.95 / 0.95 = 12.0
        result_sorted = result.sort("trade_date")
        assert len(result_sorted) == 2
        assert abs(result_sorted["close"][0] - 11.579) < 0.01  # 2024-01-02
        assert abs(result_sorted["close"][1] - 12.00) < 0.01  # 2024-01-03

    def test_qfq_with_no_adj_factor_returns_original_price(self) -> None:
        """Test QFQ with no adj_factor data returns original prices."""
        # Arrange: Write bars data without adj_factor
        bars_df = pl.DataFrame(
            {
                "sid": [1000001, 1000001],
                "trade_date": [date(2024, 1, 2), date(2024, 1, 3)],
                "open": [10.0, 11.0],
                "high": [12.0, 13.0],
                "low": [9.0, 10.0],
                "close": [11.0, 12.0],
                "volume": [1000, 2000],
            }
        )
        self.bars_store.write("stock_daily", bars_df, 2024)

        # Act: Get QFQ adjusted data (no adj_factor available)
        result = self.repo.get(
            query=BarsQuery(
                sids=[1000001],
                start="2024-01-02",
                end="2024-01-03",
                adj=AdjType.QFQ,
            )
        )

        # Assert: Should return original prices when no adj_factor data
        result_sorted = result.sort("trade_date")
        assert len(result_sorted) == 2
        assert abs(result_sorted["close"][0] - 11.0) < 0.01  # 2024-01-02
        assert abs(result_sorted["close"][1] - 12.0) < 0.01  # 2024-01-03

    def test_hfq_with_missing_adj_factor_uses_original_price(self) -> None:
        """Test HFQ adjustment falls back to original price when adj_factor missing."""
        # Arrange: Write bars data
        bars_df = pl.DataFrame(
            {
                "sid": [1000001, 1000001],
                "trade_date": [date(2024, 1, 2), date(2024, 1, 3)],
                "open": [10.0, 11.0],
                "high": [12.0, 13.0],
                "low": [9.0, 10.0],
                "close": [11.0, 12.0],
                "volume": [1000, 2000],
            }
        )
        self.bars_store.write("stock_daily", bars_df, 2024)

        # Write adj_factor data only for 2024-01-02 (missing for 2024-01-03)
        adj_df = pl.DataFrame(
            {
                "sid": [1000001],
                "trade_date": [date(2024, 1, 2)],
                "adj_factor": [0.95],
            }
        )
        self.adj_factor_store.write("adj_factor", adj_df, 2024)

        # Act: Get HFQ adjusted data
        result = self.repo.get(
            query=BarsQuery(
                sids=[1000001],
                start="2024-01-02",
                end="2024-01-03",
                adj=AdjType.HFQ,
            )
        )

        # Assert: Missing adj_factor should use original price
        # 2024-01-02: 11.0 * 0.95 = 10.45
        # 2024-01-03: 12.0 * 1.0 = 12.0 (no adj_factor, uses original)
        result_sorted = result.sort("trade_date")
        assert len(result_sorted) == 2
        assert abs(result_sorted["close"][0] - 10.45) < 0.01  # 2024-01-02
        assert (
            abs(result_sorted["close"][1] - 12.00) < 0.01
        )  # 2024-01-03 (no adj factor)

    def test_qfq_with_asof_uses_correct_baseline(self) -> None:
        """Test that QFQ with asof parameter uses correct PIT baseline."""
        # Arrange: Write bars data for 3 days
        bars_df = pl.DataFrame(
            {
                "sid": [1000001, 1000001, 1000001],
                "trade_date": [date(2024, 1, 2), date(2024, 1, 3), date(2024, 1, 4)],
                "open": [10.0, 10.0, 10.0],
                "high": [12.0, 12.0, 12.0],
                "low": [9.0, 9.0, 9.0],
                "close": [11.0, 11.0, 11.0],
                "volume": [1000, 2000, 3000],
            }
        )
        self.bars_store.write("stock_daily", bars_df, 2024)

        # Write adj_factor: 1.0, 0.95, 0.90 over the 3 days
        adj_df = pl.DataFrame(
            {
                "sid": [1000001, 1000001, 1000001],
                "trade_date": [date(2024, 1, 2), date(2024, 1, 3), date(2024, 1, 4)],
                "adj_factor": [1.0, 0.95, 0.90],
            }
        )
        self.adj_factor_store.write("adj_factor", adj_df, 2024)

        # Act: Get QFQ adjusted data with asof="2024-01-03"
        # This means: use the latest adj_factor as of 2024-01-03 (which is 0.95)
        result = self.repo.get(
            query=BarsQuery(
                sids=[1000001],
                start="2024-01-02",
                end="2024-01-04",
                adj=AdjType.QFQ,
                asof="2024-01-03",  # PIT baseline: 0.95 (last factor as of 2024-01-03)
            )
        )

        # Assert: QFQ should use 0.95 as baseline (latest factor as of 2024-01-03)
        # NOT 0.90 (latest factor in entire period)
        # Formula: adjusted = original * current / latest_asof
        # 2024-01-02: 11.0 * 1.0 / 0.95 = 11.579
        # 2024-01-03: 11.0 * 0.95 / 0.95 = 11.0
        # 2024-01-04: 11.0 * 0.90 / 0.95 = 10.421
        result_sorted = result.sort("trade_date")
        assert len(result_sorted) == 3
        assert abs(result_sorted["close"][0] - 11.579) < 0.01  # 2024-01-02
        assert abs(result_sorted["close"][1] - 11.00) < 0.01  # 2024-01-03
        assert abs(result_sorted["close"][2] - 10.421) < 0.01  # 2024-01-04


class TestBarsRepositorySingle:
    """Tests for get_single method."""

    def setup_method(self) -> None:
        """Set up test environment."""
        self.temp_dir = TemporaryDirectory()
        data_root = Path(self.temp_dir.name)

        self.pool = SQLitePool(":memory:")
        self.pool.init_schema()
        self.client = SQLiteClient(self.pool)

        self.bars_store = BarsStore(data_root)
        self.adj_factor_store = AdjFactorStore(data_root)
        self.security_store = SecurityStore(self.client)
        self.stock_status_store = StockStatusStore(data_root)  # B.3
        self.dq_engine = DQEngine()
        self.file_lock_manager = FileLockManager(data_root / "locks")
        self.quarantine_store = QuarantineStore(data_root / "quarantine.db")

        self.repo = BarsRepository(
            self.bars_store,
            self.adj_factor_store,
            self.security_store,
            self.stock_status_store,  # B.3
            self.dq_engine,
            self.file_lock_manager,
            self.quarantine_store,
        )

        # Insert test security
        self.client.execute("""
            INSERT INTO security
            (sid, symbol, name, exchange, asset_class, list_date)
            VALUES (1000001, '600000', 'Test', 'SSE', 'stock', '2000-01-01')
        """)
        self.client.execute("""
            INSERT INTO security_mapping
            (sid, source, src_code, effective_from)
            VALUES (1000001, 'tushare', '600000.SH', '2000-01-01')
        """)
        self.client.commit()

    def teardown_method(self) -> None:
        """Clean up test environment."""
        # Close SQLite connection before cleanup (Windows file lock)
        if hasattr(self, "quarantine_store"):
            self.quarantine_store.close()
        self.temp_dir.cleanup()

    def test_get_single_by_src_code(self) -> None:
        """Test get_single resolves src_code."""
        # Arrange
        test_df = pl.DataFrame(
            {
                "sid": [1000001],
                "trade_date": [date(2024, 1, 2)],
                "open": [10.0],
                "high": [12.0],
                "low": [9.0],
                "close": [11.0],
                "volume": [1000],
            }
        )
        self.bars_store.write("stock_daily", test_df, 2024)

        # Act
        result = self.repo.get_single(
            identifier="600000.SH",
            start="2024-01-01",
            end="2024-01-31",
            source="tushare",
        )

        # Assert
        assert len(result) == 1
        assert result["sid"][0] == 1000001

    def test_get_single_by_symbol(self) -> None:
        """Test get_single resolves symbol."""
        # Arrange
        test_df = pl.DataFrame(
            {
                "sid": [1000001],
                "trade_date": [date(2024, 1, 2)],
                "open": [10.0],
                "high": [12.0],
                "low": [9.0],
                "close": [11.0],
                "volume": [1000],
            }
        )
        self.bars_store.write("stock_daily", test_df, 2024)

        # Act
        result = self.repo.get_single(
            identifier="600000",
            start="2024-01-01",
            end="2024-01-31",
            source="tushare",
        )

        # Assert
        assert len(result) == 1

    def test_get_single_warns_on_multiple_symbol_matches(
        self, mocker: MockerFixture, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Test get_single warns when symbol maps to multiple SIDs."""
        # Arrange: Insert multiple securities with same symbol (unlikely but possible)
        self.client.execute("""
            INSERT INTO security
            (sid, symbol, name, exchange, asset_class, list_date)
            VALUES (1000002, '600000', 'Another Stock', 'SZSE', 'stock', '2000-01-01')
        """)
        self.client.execute("""
            INSERT INTO security_mapping
            (sid, source, src_code, effective_from)
            VALUES (1000002, 'tushare', '600000.SZ', '2000-01-01')
        """)
        self.client.commit()

        # Arrange: Write test data
        test_df = pl.DataFrame(
            {
                "sid": [1000001],
                "trade_date": [date(2024, 1, 2)],
                "open": [10.0],
                "high": [12.0],
                "low": [9.0],
                "close": [11.0],
                "volume": [1000],
            }
        )
        self.bars_store.write("stock_daily", test_df, 2024)

        # Act: Mock logger and call get_single
        mock_logger = mocker.patch("ditto_datahub.repositories.bars.repository.logger")
        result = self.repo.get_single(
            identifier="600000",
            start="2024-01-01",
            end="2024-01-31",
            source="tushare",
        )

        # Assert: Should return first SID's data
        assert len(result) == 1
        assert result["sid"][0] == 1000001

        # Assert: logger.warning should have been called with correct arguments
        mock_logger.warning.assert_called_once()
        call_args = mock_logger.warning.call_args
        assert call_args is not None
        # Extract the positional and keyword arguments
        # logger.warning(message, event=..., symbol=..., etc.)
        args, kwargs = call_args
        assert "Multiple SIDs found for symbol" in args[0]
        assert kwargs["event"] == "symbol_multiple_matches"
        assert kwargs["symbol"] == "600000"
        assert kwargs["match_count"] == 2

    def test_write_returns_write_result(self) -> None:
        """Test write returns WriteResult."""
        # Arrange
        test_df = pl.DataFrame(
            {
                "sid": [1000001],
                "trade_date": [date(2024, 1, 2)],
                "open": [10.0],
                "high": [12.0],
                "low": [9.0],
                "close": [11.0],
                "volume": [1000],
            }
        )

        # Act
        result = self.repo.write(
            df=test_df,
            year=2024,
            dataset="stock_daily",
            source="tushare",
            run_dq_check=False,
        )

        # Assert
        assert result.rows_written == 1
        assert result.file_path is not None
        assert result.checksum is not None


class TestMixedAssetClass:
    """Tests for mixed asset class handling."""

    def setup_method(self) -> None:
        """Set up test environment."""
        self.temp_dir = TemporaryDirectory()
        data_root = Path(self.temp_dir.name)

        self.pool = SQLitePool(":memory:")
        self.pool.init_schema()
        self.client = SQLiteClient(self.pool)

        self.bars_store = BarsStore(data_root)
        self.adj_factor_store = AdjFactorStore(data_root)
        self.security_store = SecurityStore(self.client)
        self.stock_status_store = StockStatusStore(data_root)  # B.3
        self.dq_engine = DQEngine()
        self.file_lock_manager = FileLockManager(data_root / "locks")
        self.quarantine_store = QuarantineStore(data_root / "quarantine.db")

        self.repo = BarsRepository(
            self.bars_store,
            self.adj_factor_store,
            self.security_store,
            self.stock_status_store,  # B.3
            self.dq_engine,
            self.file_lock_manager,
            self.quarantine_store,
        )

        # Insert stock security (SID: 100,000,000 - 199,999,999)
        self.client.execute("""
            INSERT INTO security
            (sid, symbol, name, exchange, asset_class, list_date)
            VALUES (1000001, '600000', 'Test Stock', 'SSE', 'stock', '2000-01-01')
        """)

        # Insert ETF security (SID: 200,000,000 - 299,999,999)
        self.client.execute("""
            INSERT INTO security
            (sid, symbol, name, exchange, asset_class, list_date)
            VALUES (2000001, '510300', 'Test ETF', 'SSE', 'etf', '2000-01-01')
        """)
        self.client.commit()

    def teardown_method(self) -> None:
        """Clean up test environment."""
        # Close SQLite connection before cleanup (Windows file lock)
        if hasattr(self, "quarantine_store"):
            self.quarantine_store.close()
        self.temp_dir.cleanup()

    def test_get_with_mixed_sids_raises_error(self) -> None:
        """Test that mixed stock/ETF SIDs raise ValueError."""
        # Act & Assert
        with pytest.raises(ValueError, match="检测到混合资产类别查询"):
            self.repo.get(
                query=BarsQuery(
                    sids=[1000001, 2000001],  # stock + ETF
                    start="2024-01-01",
                    end="2024-01-31",
                )
            )

    def test_get_with_all_stock_sids_succeeds(self) -> None:
        """Test that all stock SIDs succeed."""
        # Should not raise
        result = self.repo.get(
            query=BarsQuery(
                sids=[1000001, 1000002],  # both stocks
                start="2024-01-01",
                end="2024-01-31",
            )
        )
        assert isinstance(result, pl.DataFrame)

    def test_get_with_all_etf_sids_succeeds(self) -> None:
        """Test that all ETF SIDs succeed."""
        # Should not raise
        result = self.repo.get(
            query=BarsQuery(
                sids=[2000001, 2000002],  # both ETFs
                start="2024-01-01",
                end="2024-01-31",
            )
        )
        assert isinstance(result, pl.DataFrame)

    def test_get_with_all_index_sids_succeeds(self) -> None:
        """Test that all index SIDs (300M-399M) are routed to index_daily."""
        # Insert index security (SID: 300,000,000 - 399,999,999)
        self.client.execute("""
            INSERT INTO security
            (sid, symbol, name, exchange, asset_class, list_date)
            VALUES (3000001, '000001', 'Test Index', 'SSE', 'index', '2000-01-01')
        """)
        self.client.commit()

        # Write index data to index_daily dataset
        index_bars_df = pl.DataFrame(
            {
                "sid": [3000001],
                "trade_date": [date(2024, 1, 1)],
                "open": [3000.0],
                "high": [3100.0],
                "low": [2900.0],
                "close": [3050.0],
                "volume": [1000000],
            }
        )
        self.bars_store.write("index_daily", index_bars_df, 2024)

        # Should route to index_daily and return data (NOT empty from stock_daily)
        result = self.repo.get(
            query=BarsQuery(
                sids=[3000001],
                start="2024-01-01",
                end="2024-01-31",
            )
        )
        # Verify we get actual data from index_daily, not empty from wrong dataset
        assert len(result) == 1
        assert result["sid"][0] == 3000001
        assert result["close"][0] == 3050.0

    def test_get_with_mixed_index_stock_sids_raises_error(self) -> None:
        """Test that mixed index/stock SIDs raise ValueError."""
        # Insert index security
        self.client.execute("""
            INSERT INTO security
            (sid, symbol, name, exchange, asset_class, list_date)
            VALUES (3000001, '000001', 'Test Index', 'SSE', 'index', '2000-01-01')
        """)
        self.client.commit()

        # Act & Assert
        with pytest.raises(ValueError, match="检测到混合资产类别查询"):
            self.repo.get(
                query=BarsQuery(
                    sids=[1000001, 3000001],  # stock + index
                    start="2024-01-01",
                    end="2024-01-31",
                )
            )

    def test_mixed_asset_with_boundary_sids(self) -> None:
        """测试 SID 范围边界值（使用已存在的 1000001 和 2000001）."""
        # Write test data for existing SIDs from setup
        # setup already has: 1000001 (stock) and 2000001 (etf)
        stock_bars = pl.DataFrame(
            {
                "sid": [1000001],
                "trade_date": [date(2024, 1, 2)],
                "open": [10.0],
                "high": [12.0],
                "low": [9.0],
                "close": [11.0],
                "volume": [1000],
            }
        )
        etf_bars = pl.DataFrame(
            {
                "sid": [2000001],
                "trade_date": [date(2024, 1, 2)],
                "open": [5.0],
                "high": [6.0],
                "low": [4.5],
                "close": [5.5],
                "volume": [2000],
            }
        )
        self.bars_store.write("stock_daily", stock_bars, 2024)
        self.bars_store.write("etf_daily", etf_bars, 2024)

        # Act & Assert: Mixed SIDs (stock + etf) should raise error
        with pytest.raises(ValueError, match="检测到混合资产类别查询"):
            self.repo.get(
                query=BarsQuery(
                    sids=[1000001, 2000001],
                    start="2024-01-01",
                    end="2024-01-31",
                )
            )

    def test_mixed_asset_with_all_three_asset_classes(self) -> None:
        """测试同时包含 stock/etf/index 的查询."""
        # Insert index security (SID: 300,000,000 - 399,999,999)
        self.client.execute("""
            INSERT INTO security
            (sid, symbol, name, exchange, asset_class, list_date)
            VALUES (3000001, '000001', 'Test Index', 'SSE', 'index', '2000-01-01')
        """)
        self.client.commit()

        # Write index data
        index_bars = pl.DataFrame(
            {
                "sid": [3000001],
                "trade_date": [date(2024, 1, 1)],
                "open": [3000.0],
                "high": [3100.0],
                "low": [2900.0],
                "close": [3050.0],
                "volume": [1000000],
            }
        )
        self.bars_store.write("index_daily", index_bars, 2024)

        # Act & Assert: All three asset classes should raise error
        with pytest.raises(ValueError, match="检测到混合资产类别查询"):
            self.repo.get(
                query=BarsQuery(
                    sids=[1000001, 2000001, 3000001],  # stock + etf + index
                    start="2024-01-01",
                    end="2024-01-31",
                )
            )

        # Verify error message mentions all three classes
        try:
            self.repo.get(
                query=BarsQuery(
                    sids=[1000001, 2000001, 3000001],
                    start="2024-01-01",
                    end="2024-01-31",
                )
            )
        except ValueError as e:
            error_msg = str(e)
            assert "stock" in error_msg
            assert "ETF" in error_msg
            assert "index" in error_msg
        else:
            pytest.fail("Expected ValueError for mixed asset classes")


class TestAdjFactorEdgeCases:
    """复权因子边缘情况测试."""

    def setup_method(self) -> None:
        """Set up test environment."""
        self.temp_dir = TemporaryDirectory()
        data_root = Path(self.temp_dir.name)

        self.pool = SQLitePool(":memory:")
        self.pool.init_schema()
        self.client = SQLiteClient(self.pool)

        self.bars_store = BarsStore(data_root)
        self.adj_factor_store = AdjFactorStore(data_root)
        self.security_store = SecurityStore(self.client)
        self.stock_status_store = StockStatusStore(data_root)  # B.3
        self.dq_engine = DQEngine()
        self.file_lock_manager = FileLockManager(data_root / "locks")
        self.quarantine_store = QuarantineStore(data_root / "quarantine.db")

        self.repo = BarsRepository(
            self.bars_store,
            self.adj_factor_store,
            self.security_store,
            self.stock_status_store,  # B.3
            self.dq_engine,
            self.file_lock_manager,
            self.quarantine_store,
        )

        # Insert test security
        self.client.execute("""
            INSERT INTO security
            (sid, symbol, name, exchange, asset_class, list_date)
            VALUES (1000001, '600000', 'Test Stock', 'SSE', 'stock', '2000-01-01')
        """)
        self.client.commit()

    def teardown_method(self) -> None:
        """Clean up test environment."""
        # Close SQLite connection before cleanup (Windows file lock)
        if hasattr(self, "quarantine_store"):
            self.quarantine_store.close()
        self.temp_dir.cleanup()

    def test_qfq_with_all_missing_factors_returns_original(self) -> None:
        """QFQ 所有复权因子缺失时返回原始价格."""
        # Arrange: Write bars data without any adj_factor
        bars_df = pl.DataFrame(
            {
                "sid": [1000001, 1000001],
                "trade_date": [date(2024, 1, 2), date(2024, 1, 3)],
                "open": [10.0, 11.0],
                "high": [12.0, 13.0],
                "low": [9.0, 10.0],
                "close": [11.0, 12.0],
                "volume": [1000, 2000],
            }
        )
        self.bars_store.write("stock_daily", bars_df, 2024)

        # Act: Get QFQ adjusted data (no adj_factor data at all)
        result = self.repo.get(
            query=BarsQuery(
                sids=[1000001],
                start="2024-01-02",
                end="2024-01-03",
                adj=AdjType.QFQ,
            )
        )

        # Assert: Should return original prices when no adj_factor data exists
        result_sorted = result.sort("trade_date")
        assert len(result_sorted) == 2
        assert abs(result_sorted["close"][0] - 11.0) < 0.01  # 2024-01-02
        assert abs(result_sorted["close"][1] - 12.0) < 0.01  # 2024-01-03

    def test_hfq_with_all_missing_factors_returns_original(self) -> None:
        """HFQ 所有复权因子缺失时返回原始价格."""
        # Arrange: Write bars data without any adj_factor
        bars_df = pl.DataFrame(
            {
                "sid": [1000001, 1000001],
                "trade_date": [date(2024, 1, 2), date(2024, 1, 3)],
                "open": [10.0, 11.0],
                "high": [12.0, 13.0],
                "low": [9.0, 10.0],
                "close": [11.0, 12.0],
                "volume": [1000, 2000],
            }
        )
        self.bars_store.write("stock_daily", bars_df, 2024)

        # Act: Get HFQ adjusted data (no adj_factor data at all)
        result = self.repo.get(
            query=BarsQuery(
                sids=[1000001],
                start="2024-01-02",
                end="2024-01-03",
                adj=AdjType.HFQ,
            )
        )

        # Assert: Should return original prices when no adj_factor data exists
        result_sorted = result.sort("trade_date")
        assert len(result_sorted) == 2
        assert abs(result_sorted["close"][0] - 11.0) < 0.01  # 2024-01-02
        assert abs(result_sorted["close"][1] - 12.0) < 0.01  # 2024-01-03

    def test_qfq_year_boundary_continuity(self) -> None:
        """QFQ 跨年数据排序连续性验证."""
        # Arrange: Write bars data across year boundary
        dates = [date(2023, 12, 29), date(2023, 12, 30), date(2024, 1, 2)]
        bars_df = pl.DataFrame(
            {
                "sid": [1000001, 1000001, 1000001],
                "trade_date": dates,
                "open": [10.0, 10.0, 10.0],
                "high": [12.0, 12.0, 12.0],
                "low": [9.0, 9.0, 9.0],
                "close": [11.0, 11.0, 11.0],
                "volume": [1000, 2000, 3000],
            }
        )
        # Split data by year
        bars_2023 = bars_df.filter(pl.col("trade_date") < date(2024, 1, 1))
        bars_2024 = bars_df.filter(pl.col("trade_date") >= date(2024, 1, 1))
        self.bars_store.write("stock_daily", bars_2023, 2023)
        self.bars_store.write("stock_daily", bars_2024, 2024)

        # Write adj_factor data: 0.95 starting from 2024-01-02
        adj_df_2023 = pl.DataFrame(
            {
                "sid": [1000001, 1000001],
                "trade_date": [date(2023, 12, 29), date(2023, 12, 30)],
                "adj_factor": [1.0, 1.0],
            }
        )
        adj_df_2024 = pl.DataFrame(
            {
                "sid": [1000001],
                "trade_date": [date(2024, 1, 2)],
                "adj_factor": [0.95],
            }
        )
        self.adj_factor_store.write("adj_factor", adj_df_2023, 2023)
        self.adj_factor_store.write("adj_factor", adj_df_2024, 2024)

        # Act: Get QFQ adjusted data across year boundary
        result = self.repo.get(
            query=BarsQuery(
                sids=[1000001],
                start="2023-12-29",
                end="2024-01-02",
                adj=AdjType.QFQ,
            )
        )

        # Assert: Verify continuity across year boundary
        result_sorted = result.sort("trade_date")
        assert len(result_sorted) == 3
        # QFQ should use latest factor (0.95) as baseline for all dates
        # 2023-12-29: 11.0 * 1.0 / 0.95
        assert abs(result_sorted["close"][0] - 11.579) < 0.01
        # 2023-12-30: 11.0 * 1.0 / 0.95
        assert abs(result_sorted["close"][1] - 11.579) < 0.01
        # 2024-01-02: 11.0 * 0.95 / 0.95
        assert abs(result_sorted["close"][2] - 11.00) < 0.01

    def test_qfq_large_dataset_performance(self) -> None:
        """QFQ 大数据集性能测试（365 个交易日）."""
        # Arrange: Create dataset for full year (365 trading days)
        random.seed(42)
        # Generate dates for full year 2024
        dates = [date(2024, 1, 1) + timedelta(days=i) for i in range(365)]
        n_records = len(dates)
        sids = [1000001] * n_records
        opens = [10.0 + random.random() for _ in range(n_records)]
        highs = [12.0 + random.random() for _ in range(n_records)]
        lows = [9.0 + random.random() for _ in range(n_records)]
        closes = [11.0 + random.random() for _ in range(n_records)]
        volumes = [1000 + i for i in range(n_records)]

        bars_df = pl.DataFrame(
            {
                "sid": sids,
                "trade_date": dates,
                "open": opens,
                "high": highs,
                "low": lows,
                "close": closes,
                "volume": volumes,
            }
        )
        self.bars_store.write("stock_daily", bars_df, 2024)

        # Create adj_factor data for all dates
        half_len = len(dates) // 2
        adj_factors = [1.0 if i < half_len else 0.95 for i in range(len(dates))]
        adj_df = pl.DataFrame(
            {
                "sid": [1000001] * len(dates),
                "trade_date": dates,
                "adj_factor": adj_factors,
            }
        )
        self.adj_factor_store.write("adj_factor", adj_df, 2024)

        # Act: Get QFQ adjusted data for full year
        start_time = time.time()
        result = self.repo.get(
            query=BarsQuery(
                sids=[1000001],
                start="2024-01-01",
                end="2024-12-31",
                adj=AdjType.QFQ,
            )
        )
        duration_ms = (time.time() - start_time) * 1000

        # Assert: Verify results and performance
        assert len(result) == n_records
        # Performance check: should complete within reasonable time (< 5 seconds)
        msg = f"Performance check failed: {duration_ms}ms >= 5000ms"
        assert duration_ms < 5000, msg

    def test_adj_factor_with_single_sid(self) -> None:
        """单个 SID 的复权处理."""
        # Arrange: Write bars and adj_factor for single SID
        bars_df = pl.DataFrame(
            {
                "sid": [1000001],
                "trade_date": [date(2024, 1, 2)],
                "open": [10.0],
                "high": [12.0],
                "low": [9.0],
                "close": [11.0],
                "volume": [1000],
            }
        )
        self.bars_store.write("stock_daily", bars_df, 2024)

        adj_df = pl.DataFrame(
            {
                "sid": [1000001],
                "trade_date": [date(2024, 1, 2)],
                "adj_factor": [0.95],
            }
        )
        self.adj_factor_store.write("adj_factor", adj_df, 2024)

        # Act: Get QFQ adjusted data
        result = self.repo.get(
            query=BarsQuery(
                sids=[1000001],
                start="2024-01-02",
                end="2024-01-02",
                adj=AdjType.QFQ,
            )
        )

        # Assert: Single SID should work correctly
        assert len(result) == 1
        # QFQ: 11.0 * 0.95 / 0.95 = 11.0 (only one factor, so baseline is same)
        assert abs(result["close"][0] - 11.0) < 0.01

    def test_adj_factor_with_empty_sid_list(self) -> None:
        """空 SID 列表处理."""
        # Arrange: Write some bars data
        bars_df = pl.DataFrame(
            {
                "sid": [1000001],
                "trade_date": [date(2024, 1, 2)],
                "open": [10.0],
                "high": [12.0],
                "low": [9.0],
                "close": [11.0],
                "volume": [1000],
            }
        )
        self.bars_store.write("stock_daily", bars_df, 2024)

        # Act: Get data with empty SID list
        result = self.repo.get(
            query=BarsQuery(
                sids=[],
                start="2024-01-01",
                end="2024-01-31",
            )
        )

        # Assert: Should return empty DataFrame
        assert isinstance(result, pl.DataFrame)
        assert result.is_empty()


class TestMarketWideMode:
    """Tests for market_wide query mode."""

    def setup_method(self) -> None:
        """Set up test environment with multiple securities."""
        self.temp_dir = TemporaryDirectory()
        data_root = Path(self.temp_dir.name)

        self.pool = SQLitePool(":memory:")
        self.pool.init_schema()
        self.client = SQLiteClient(self.pool)

        self.bars_store = BarsStore(data_root)
        self.adj_factor_store = AdjFactorStore(data_root)
        self.security_store = SecurityStore(self.client)
        self.stock_status_store = StockStatusStore(data_root)
        self.dq_engine = DQEngine()
        self.file_lock_manager = FileLockManager(data_root / "locks")
        self.quarantine_store = QuarantineStore(data_root / "quarantine.db")

        self.repo = BarsRepository(
            self.bars_store,
            self.adj_factor_store,
            self.security_store,
            self.stock_status_store,
            self.dq_engine,
            self.file_lock_manager,
            self.quarantine_store,
        )

        # Insert multiple active stocks
        self.client.execute("""
            INSERT INTO security
            (sid, symbol, name, exchange, asset_class, list_date, is_active)
            VALUES
            (1000001, '600000', 'Stock1', 'SSE', 'stock', '2000-01-01', 1),
            (1000002, '600001', 'Stock2', 'SSE', 'stock', '2000-01-01', 1),
            (1000003, '600002', 'Stock3', 'SSE', 'stock', '2000-01-01', 0)
        """)
        self.client.commit()

    def teardown_method(self) -> None:
        """Clean up test environment."""
        # Close SQLite connection before cleanup (Windows file lock)
        if hasattr(self, "quarantine_store"):
            self.quarantine_store.close()
        self.temp_dir.cleanup()

    def test_market_wide_returns_all_active_stocks(self) -> None:
        """Test market_wide=True returns data for all active stocks."""
        # Arrange: Write bars data for all stocks
        bars_df = pl.DataFrame(
            {
                "sid": [1000001, 1000002, 1000003],
                "trade_date": [date(2024, 1, 2)] * 3,
                "open": [10.0, 11.0, 12.0],
                "high": [12.0, 13.0, 14.0],
                "low": [9.0, 10.0, 11.0],
                "close": [11.0, 12.0, 13.0],
                "volume": [1000, 2000, 3000],
            }
        )
        self.bars_store.write("stock_daily", bars_df, 2024)

        # Act: Query with market_wide=True
        result = self.repo.get(
            query=BarsQuery(
                market_wide=True,
                start="2024-01-01",
                end="2024-01-31",
            )
        )

        # Assert: Should return data for active stocks only (1000001, 1000002)
        assert not result.is_empty()
        result_sids = result["sid"].unique().to_list()
        assert 1000001 in result_sids
        assert 1000002 in result_sids
        assert 1000003 not in result_sids  # Inactive stock

    def test_market_wide_respects_asset_class_filter(self) -> None:
        """Test market_wide=True with asset_class filter."""
        # Arrange: Insert ETF
        self.client.execute("""
            INSERT INTO security
            (sid, symbol, name, exchange, asset_class, list_date, is_active)
            VALUES (2000001, '510300', 'Test ETF', 'SSE', 'etf', '2000-01-01', 1)
        """)
        self.client.commit()

        # Write stock data
        stock_bars = pl.DataFrame(
            {
                "sid": [1000001],
                "trade_date": [date(2024, 1, 2)],
                "open": [10.0],
                "high": [12.0],
                "low": [9.0],
                "close": [11.0],
                "volume": [1000],
            }
        )
        self.bars_store.write("stock_daily", stock_bars, 2024)

        # Write ETF data
        etf_bars = pl.DataFrame(
            {
                "sid": [2000001],
                "trade_date": [date(2024, 1, 2)],
                "open": [5.0],
                "high": [6.0],
                "low": [4.5],
                "close": [5.5],
                "volume": [2000],
            }
        )
        self.bars_store.write("etf_daily", etf_bars, 2024)

        # Act: Query with market_wide=True and asset_class="stock"
        result = self.repo.get(
            query=BarsQuery(
                market_wide=True,
                asset_class="stock",
                start="2024-01-01",
                end="2024-01-31",
            )
        )

        # Assert: Should only return stock data
        assert not result.is_empty()
        result_sids = result["sid"].unique().to_list()
        assert 1000001 in result_sids
        assert 2000001 not in result_sids

    def test_sample_set_mode_unchanged(self) -> None:
        """Test that sample set mode (market_wide=False) works as before."""
        # Arrange: Write bars data
        bars_df = pl.DataFrame(
            {
                "sid": [1000001, 1000002],
                "trade_date": [date(2024, 1, 2)] * 2,
                "open": [10.0, 11.0],
                "high": [12.0, 13.0],
                "low": [9.0, 10.0],
                "close": [11.0, 12.0],
                "volume": [1000, 2000],
            }
        )
        self.bars_store.write("stock_daily", bars_df, 2024)

        # Act: Query with specific SIDs (sample set mode)
        result = self.repo.get(
            query=BarsQuery(
                sids=[1000001],
                market_wide=False,
                start="2024-01-01",
                end="2024-01-31",
            )
        )

        # Assert: Should only return data for specified SID
        assert not result.is_empty()
        result_sids = result["sid"].unique().to_list()
        assert result_sids == [1000001]
        assert 1000002 not in result_sids

    def test_market_wide_with_no_active_stocks(self) -> None:
        """Test market_wide=True when no active stocks exist."""
        # Arrange: Deactivate all stocks
        self.client.execute("UPDATE security SET is_active = 0")
        self.client.commit()

        # Act: Query with market_wide=True
        result = self.repo.get(
            query=BarsQuery(
                market_wide=True,
                start="2024-01-01",
                end="2024-01-31",
            )
        )

        # Assert: Should return empty DataFrame
        assert isinstance(result, pl.DataFrame)
        assert result.is_empty()

    def test_market_wide_with_no_data(self) -> None:
        """Test market_wide=True when no bars data exists."""
        # Act: Query with market_wide=True (no data written)
        result = self.repo.get(
            query=BarsQuery(
                market_wide=True,
                start="2024-01-01",
                end="2024-01-31",
            )
        )

        # Assert: Should return empty DataFrame
        assert isinstance(result, pl.DataFrame)
        assert result.is_empty()
