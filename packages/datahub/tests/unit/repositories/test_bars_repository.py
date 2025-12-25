"""Tests for BarsRepository."""

from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory

import polars as pl
from ditto_datahub.repositories.bars import BarsRepository
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
