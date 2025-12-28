"""Tests for BarsRepository."""

from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import polars as pl
import pytest
from ditto_datahub.repositories.bars import AdjType, BarsRepository
from ditto_datahub.runtime.dq_checker import DQChecker
from ditto_datahub.runtime.file_lock import FileLockManager
from ditto_datahub.runtime.sqlite_pool import SQLitePool
from ditto_datahub.stores.adj_factor_store import AdjFactorStore
from ditto_datahub.stores.bars_store import BarsStore
from ditto_datahub.stores.security_store import SecurityStore
from ditto_datahub.stores.sqlite_client import SQLiteClient


class TestBarsRepository:
    """Tests for BarsRepository."""

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
        self.dq_checker = DQChecker()
        self.file_lock_manager = FileLockManager(data_root / "locks")

        self.repo = BarsRepository(
            self.bars_store,
            self.adj_factor_store,
            self.security_store,
            self.dq_checker,
            self.file_lock_manager,
        )

        # Insert test security
        self.client.execute("""
            INSERT INTO security
            (sid, symbol, name, exchange, asset_class, list_date)
            VALUES (100000001, '600000', 'Test', 'SSE', 'stock', '2000-01-01')
        """)
        self.client.execute("""
            INSERT INTO security_mapping
            (sid, source, src_code, effective_from)
            VALUES (100000001, 'tushare', '600000.SH', '2000-01-01')
        """)
        self.client.commit()

    def teardown_method(self) -> None:
        """Clean up test environment."""
        self.temp_dir.cleanup()

    def test_get_returns_empty_dataframe_for_no_data(self) -> None:
        """Test get returns empty DataFrame when no data exists."""
        result = self.repo.get(
            sids=[100000001],
            start="2024-01-01",
            end="2024-01-31",
        )

        assert isinstance(result, pl.DataFrame)
        assert result.is_empty()

    def test_get_returns_bars_data(self) -> None:
        """Test get returns bars data."""
        # Arrange
        test_df = pl.DataFrame(
            {
                "sid": [100000001, 100000001],
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
            sids=[100000001],
            start="2024-01-01",
            end="2024-01-31",
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
                "sid": [100000001],
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
            sids=[100000001],
            start="2024-01-01",
            end="2024-01-31",
            with_symbol=True,
        )

        # Assert
        assert "symbol" in result.columns
        assert result["symbol"][0] == "600000"


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
        self.dq_checker = DQChecker()
        self.file_lock_manager = FileLockManager(data_root / "locks")

        self.repo = BarsRepository(
            self.bars_store,
            self.adj_factor_store,
            self.security_store,
            self.dq_checker,
            self.file_lock_manager,
        )

        # Insert test security
        self.client.execute("""
            INSERT INTO security
            (sid, symbol, name, exchange, asset_class, list_date)
            VALUES (100000001, '600000', 'Test Stock', 'SSE', 'stock', '2000-01-01')
        """)
        self.client.commit()

    def teardown_method(self) -> None:
        """Clean up test environment."""
        self.temp_dir.cleanup()

    def test_qfq_uses_latest_adj_factor(self) -> None:
        """Test that QFQ adjustment uses the latest adj_factor correctly."""
        # Arrange: Write bars data with consistent prices
        bars_df = pl.DataFrame(
            {
                "sid": [100000001, 100000001, 100000001],
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
                "sid": [100000001, 100000001, 100000001],
                "trade_date": [date(2024, 1, 2), date(2024, 1, 3), date(2024, 1, 4)],
                "adj_factor": [1.0, 0.95, 0.95],
            }
        )
        self.adj_factor_store.write("adj_factor", adj_df, 2024)

        # Act: Get QFQ adjusted data
        result = self.repo.get(
            sids=[100000001],
            start="2024-01-02",
            end="2024-01-04",
            adj=AdjType.QFQ,
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
                "sid": [100000001, 100000001],
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
                "sid": [100000001],
                "trade_date": [date(2024, 1, 3)],
                "adj_factor": [0.95],
            }
        )
        self.adj_factor_store.write("adj_factor", adj_df, 2024)

        # Act: Get QFQ adjusted data
        result = self.repo.get(
            sids=[100000001],
            start="2024-01-02",
            end="2024-01-03",
            adj=AdjType.QFQ,
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
                "sid": [100000001, 100000001],
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
            sids=[100000001],
            start="2024-01-02",
            end="2024-01-03",
            adj=AdjType.QFQ,
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
                "sid": [100000001, 100000001],
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
                "sid": [100000001],
                "trade_date": [date(2024, 1, 2)],
                "adj_factor": [0.95],
            }
        )
        self.adj_factor_store.write("adj_factor", adj_df, 2024)

        # Act: Get HFQ adjusted data
        result = self.repo.get(
            sids=[100000001],
            start="2024-01-02",
            end="2024-01-03",
            adj=AdjType.HFQ,
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
        self.dq_checker = DQChecker()
        self.file_lock_manager = FileLockManager(data_root / "locks")

        self.repo = BarsRepository(
            self.bars_store,
            self.adj_factor_store,
            self.security_store,
            self.dq_checker,
            self.file_lock_manager,
        )

        # Insert test security
        self.client.execute("""
            INSERT INTO security
            (sid, symbol, name, exchange, asset_class, list_date)
            VALUES (100000001, '600000', 'Test', 'SSE', 'stock', '2000-01-01')
        """)
        self.client.execute("""
            INSERT INTO security_mapping
            (sid, source, src_code, effective_from)
            VALUES (100000001, 'tushare', '600000.SH', '2000-01-01')
        """)
        self.client.commit()

    def teardown_method(self) -> None:
        """Clean up test environment."""
        self.temp_dir.cleanup()

    def test_get_single_by_src_code(self) -> None:
        """Test get_single resolves src_code."""
        # Arrange
        test_df = pl.DataFrame(
            {
                "sid": [100000001],
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
        assert result["sid"][0] == 100000001

    def test_get_single_by_symbol(self) -> None:
        """Test get_single resolves symbol."""
        # Arrange
        test_df = pl.DataFrame(
            {
                "sid": [100000001],
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
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Test get_single warns when symbol maps to multiple SIDs."""
        # Arrange: Insert multiple securities with same symbol (unlikely but possible)
        self.client.execute("""
            INSERT INTO security
            (sid, symbol, name, exchange, asset_class, list_date)
            VALUES (100000002, '600000', 'Another Stock', 'SZSE', 'stock', '2000-01-01')
        """)
        self.client.execute("""
            INSERT INTO security_mapping
            (sid, source, src_code, effective_from)
            VALUES (100000002, 'tushare', '600000.SZ', '2000-01-01')
        """)
        self.client.commit()

        # Arrange: Write test data
        test_df = pl.DataFrame(
            {
                "sid": [100000001],
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
        with patch("ditto_datahub.repositories.bars.logger") as mock_logger:
            result = self.repo.get_single(
                identifier="600000",
                start="2024-01-01",
                end="2024-01-31",
                source="tushare",
            )

        # Assert: Should return first SID's data
        assert len(result) == 1
        assert result["sid"][0] == 100000001

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
                "sid": [100000001],
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
        self.dq_checker = DQChecker()
        self.file_lock_manager = FileLockManager(data_root / "locks")

        self.repo = BarsRepository(
            self.bars_store,
            self.adj_factor_store,
            self.security_store,
            self.dq_checker,
            self.file_lock_manager,
        )

        # Insert stock security (SID: 100,000,000 - 199,999,999)
        self.client.execute("""
            INSERT INTO security
            (sid, symbol, name, exchange, asset_class, list_date)
            VALUES (100000001, '600000', 'Test Stock', 'SSE', 'stock', '2000-01-01')
        """)

        # Insert ETF security (SID: 200,000,000 - 299,999,999)
        self.client.execute("""
            INSERT INTO security
            (sid, symbol, name, exchange, asset_class, list_date)
            VALUES (200000001, '510300', 'Test ETF', 'SSE', 'etf', '2000-01-01')
        """)
        self.client.commit()

    def teardown_method(self) -> None:
        """Clean up test environment."""
        self.temp_dir.cleanup()

    def test_get_with_mixed_sids_raises_error(self) -> None:
        """Test that mixed stock/ETF SIDs raise ValueError."""
        # Act & Assert
        with pytest.raises(ValueError, match="Mixed asset class query"):
            self.repo.get(
                sids=[100000001, 200000001],  # stock + ETF
                start="2024-01-01",
                end="2024-01-31",
            )

    def test_get_with_all_stock_sids_succeeds(self) -> None:
        """Test that all stock SIDs succeed."""
        # Should not raise
        result = self.repo.get(
            sids=[100000001, 100000002],  # both stocks
            start="2024-01-01",
            end="2024-01-31",
        )
        assert isinstance(result, pl.DataFrame)

    def test_get_with_all_etf_sids_succeeds(self) -> None:
        """Test that all ETF SIDs succeed."""
        # Should not raise
        result = self.repo.get(
            sids=[200000001, 200000002],  # both ETFs
            start="2024-01-01",
            end="2024-01-31",
        )
        assert isinstance(result, pl.DataFrame)

    def test_get_with_all_index_sids_succeeds(self) -> None:
        """Test that all index SIDs (300M-399M) are routed to index_daily."""
        # Insert index security (SID: 300,000,000 - 399,999,999)
        self.client.execute("""
            INSERT INTO security
            (sid, symbol, name, exchange, asset_class, list_date)
            VALUES (300000001, '000001', 'Test Index', 'SSE', 'index', '2000-01-01')
        """)
        self.client.commit()

        # Write index data to index_daily dataset
        index_bars_df = pl.DataFrame(
            {
                "sid": [300000001],
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
            sids=[300000001],
            start="2024-01-01",
            end="2024-01-31",
        )
        # Verify we get actual data from index_daily, not empty from wrong dataset
        assert len(result) == 1
        assert result["sid"][0] == 300000001
        assert result["close"][0] == 3050.0

    def test_get_with_mixed_index_stock_sids_raises_error(self) -> None:
        """Test that mixed index/stock SIDs raise ValueError."""
        # Insert index security
        self.client.execute("""
            INSERT INTO security
            (sid, symbol, name, exchange, asset_class, list_date)
            VALUES (300000001, '000001', 'Test Index', 'SSE', 'index', '2000-01-01')
        """)
        self.client.commit()

        # Act & Assert
        with pytest.raises(ValueError, match="Mixed asset class query"):
            self.repo.get(
                sids=[100000001, 300000001],  # stock + index
                start="2024-01-01",
                end="2024-01-31",
            )
