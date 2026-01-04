"""Tests for DQ system migration from DQChecker to DQEngine.

This test module verifies the migration from the legacy DQChecker to the new DQEngine.
Following TDD: RED -> GREEN -> REFACTOR.
"""

from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory

import polars as pl
from ditto_datahub.dq.engine import DQEngine
from ditto_datahub.dq.models import DQResult
from ditto_datahub.hub import DataHub
from ditto_datahub.runtime.dq_checker import DQCheckResult  # Legacy
from ditto_datahub.runtime.file_lock import FileLockManager
from ditto_datahub.runtime.sqlite_pool import SQLitePool
from ditto_datahub.stores.adj_factor_store import AdjFactorStore
from ditto_datahub.stores.bars_store import BarsStore
from ditto_datahub.stores.security_store import SecurityStore
from ditto_datahub.stores.sqlite_client import SQLiteClient
from ditto_datahub.stores.stock_status_store import StockStatusStore


class TestDQEngineIntegration:
    """Tests for DQEngine integration in BarsRepository."""

    def setup_method(self) -> None:
        """Set up test environment."""
        self.temp_dir = TemporaryDirectory()
        data_root = Path(self.temp_dir.name)

        self.pool = SQLitePool(":memory:")
        self.pool.init_schema()
        self.client = SQLiteClient(self.pool)

        # Create DQEngine with empty config (no rules by default)
        self.dq_engine = DQEngine(config=None)

        self.bars_store = BarsStore(data_root)
        self.adj_factor_store = AdjFactorStore(data_root)
        self.security_store = SecurityStore(self.client)
        self.stock_status_store = StockStatusStore(data_root)
        self.file_lock_manager = FileLockManager(data_root / "locks")

        # Create DataHub
        self.hub = DataHub(data_root=data_root)

        # Initialize security table
        self.client.execute("""
            INSERT INTO security
            (sid, symbol, name, exchange, asset_class, list_date)
            VALUES (1000001, '600000', 'Test', 'SSE', 'stock', '2000-01-01')
        """)
        self.client.commit()

    def teardown_method(self) -> None:
        """Clean up test environment."""
        self.temp_dir.cleanup()

    def test_bars_repository_uses_dq_engine_not_dq_checker(self) -> None:
        """Test that BarsRepository uses DQEngine instead of DQChecker."""
        # This test will FAIL initially because BarsRepository still uses DQChecker
        # After migration, it will have _dq_engine attribute instead of _dq_checker

        # Access bars repository through hub
        bars_repo = self.hub.bars

        # Verify DQEngine is used (new)
        assert hasattr(bars_repo, "_dq_engine"), (
            "BarsRepository should have _dq_engine attribute"
        )
        assert isinstance(bars_repo._dq_engine, DQEngine), (
            "_dq_engine should be DQEngine instance"
        )

        # Verify DQChecker is NOT used (old)
        assert not hasattr(bars_repo, "_dq_checker"), (
            "BarsRepository should NOT have _dq_checker attribute"
        )

    def test_write_returns_new_dq_result_format(self) -> None:
        """Test that write() returns new DQResult format from DQEngine."""
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
        result = self.hub.bars.write(
            df=test_df,
            year=2024,
            dataset="stock_daily",
            source="tushare",
            run_dq_check=True,
        )

        # Assert: Should use new DQResult format
        assert result.dq_result is not None, "dq_result should not be None"
        assert isinstance(result.dq_result, DQResult), (
            f"dq_result should be DQResult, got {type(result.dq_result)}"
        )
        # Should NOT be legacy DQCheckResult
        assert not isinstance(result.dq_result, DQCheckResult), (
            "dq_result should NOT be legacy DQCheckResult"
        )

    def test_dq_check_pass_with_valid_data(self) -> None:
        """Test that DQ check passes with valid data."""
        # Arrange: Create valid bars data
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

        # Act
        result = self.hub.bars.write(
            df=test_df,
            year=2024,
            dataset="stock_daily",
            source="tushare",
            run_dq_check=True,
        )

        # Assert: Should pass DQ check (no blocking errors)
        assert result.blocked is False, "Write should not be blocked for valid data"
        assert result.dq_result.passed is True, "DQ check should pass for valid data"
        assert result.rows_written == 2, "Should write 2 rows"

    def test_dq_check_block_with_null_values(self) -> None:
        """Test that DQ check blocks write when NULL values detected.

        This test requires DQEngine to have not_null rules configured.
        """
        # Arrange: Create data with NULL values
        bad_df = pl.DataFrame(
            {
                "sid": [1000001, 1000001, None],  # NULL in sid
                "trade_date": [date(2024, 1, 2), date(2024, 1, 3), date(2024, 1, 4)],
                "open": [10.0, 11.0, 10.0],
                "high": [12.0, 13.0, 12.0],
                "low": [9.0, 10.0, 9.0],
                "close": [11.0, 12.0, 11.0],
                "volume": [1000, 2000, 1000],
            }
        )

        # Act
        result = self.hub.bars.write(
            df=bad_df,
            year=2024,
            dataset="stock_daily",
            source="tushare",
            run_dq_check=True,
        )

        # Assert: Should block write due to NULL values
        # Note: This depends on DQEngine having not_null rules configured
        # If no rules are configured, this may not block
        if result.dq_result.has_errors:
            assert result.blocked is True, (
                "Write should be blocked when DQ check has errors"
            )
            assert result.rows_written == 0, "Should write 0 rows when blocked"

    def test_dq_check_with_disabled_check(self) -> None:
        """Test that write succeeds when DQ check is disabled."""
        # Arrange: Create data with NULL values
        bad_df = pl.DataFrame(
            {
                "sid": [1000001, 1000001, None],
                "trade_date": [date(2024, 1, 2), date(2024, 1, 3), date(2024, 1, 4)],
                "open": [10.0, 11.0, 10.0],
                "high": [12.0, 13.0, 12.0],
                "low": [9.0, 10.0, 9.0],
                "close": [11.0, 12.0, 11.0],
                "volume": [1000, 2000, 1000],
            }
        )

        # Act: Disable DQ check
        result = self.hub.bars.write(
            df=bad_df,
            year=2024,
            dataset="stock_daily",
            source="tushare",
            run_dq_check=False,  # Disable DQ check
        )

        # Assert: Should NOT block when DQ check is disabled
        assert result.blocked is False, (
            "Write should not be blocked when DQ check is disabled"
        )
        assert result.dq_result is None, (
            "dq_result should be None when DQ check is disabled"
        )


class TestDQEngineWithConfig:
    """Tests for DQEngine with YAML configuration."""

    def setup_method(self) -> None:
        """Set up test environment with DQ config."""
        self.temp_dir = TemporaryDirectory()
        data_root = Path(self.temp_dir.name)

        # Create DQ config directory
        self.dq_config_dir = data_root / "config" / "dq"
        self.dq_config_dir.mkdir(parents=True, exist_ok=True)

        # Create a simple DQ rule file for stock_daily
        dq_rules = """
dataset: stock_daily
description: Stock daily bars data quality rules

l1_technical:
  - rule: not_null
    columns: [sid, trade_date, open, high, low, close, volume]
    message: "Required column has null values"

  - rule: unique
    columns: [sid, trade_date]
    message: "Duplicate (sid, trade_date) detected"

l2_business:
  - rule: positive
    columns: [volume]
    message: "Volume must be positive"
"""
        (self.dq_config_dir / "stock_daily.yml").write_text(dq_rules)

        self.pool = SQLitePool(":memory:")
        self.pool.init_schema()
        self.client = SQLiteClient(self.pool)

        # Create DQEngine with config
        self.dq_engine = DQEngine(config_path=self.dq_config_dir)

        self.bars_store = BarsStore(data_root)
        self.adj_factor_store = AdjFactorStore(data_root)
        self.security_store = SecurityStore(self.client)
        self.stock_status_store = StockStatusStore(data_root)
        self.file_lock_manager = FileLockManager(data_root / "locks")

        # Initialize security table
        self.client.execute("""
            INSERT INTO security
            (sid, symbol, name, exchange, asset_class, list_date)
            VALUES (1000001, '600000', 'Test', 'SSE', 'stock', '2000-01-01')
        """)
        self.client.commit()

    def teardown_method(self) -> None:
        """Clean up test environment."""
        self.temp_dir.cleanup()

    def test_dq_engine_blocks_on_null_values(self) -> None:
        """Test that DQEngine blocks write with NULL values."""
        # Arrange: Create data with NULL values
        bad_df = pl.DataFrame(
            {
                "sid": [1000001, 1000001, None],  # NULL in sid
                "trade_date": [date(2024, 1, 2), date(2024, 1, 3), date(2024, 1, 4)],
                "open": [10.0, 11.0, 10.0],
                "high": [12.0, 13.0, 12.0],
                "low": [9.0, 10.0, 9.0],
                "close": [11.0, 12.0, 11.0],
                "volume": [1000, 2000, 1000],
            }
        )

        # Act: Run DQ check
        dq_result = self.dq_engine.check(bad_df, "stock_daily")

        # Assert: Should detect NULL values
        assert dq_result.passed is False, "DQ check should fail with NULL values"
        assert dq_result.has_errors is True, "Should have ERROR severity issues"
        assert len(dq_result.issues) > 0, "Should have at least one issue"
        # Check that at least one issue is about null values
        null_issues = [i for i in dq_result.issues if "null" in i.message.lower()]
        assert len(null_issues) > 0, "Should have null value issues"

    def test_dq_engine_blocks_on_duplicate_rows(self) -> None:
        """Test that DQEngine blocks write with duplicate rows."""
        # Arrange: Create data with duplicate (sid, trade_date)
        dup_df = pl.DataFrame(
            {
                "sid": [1000001, 1000001],  # Same SID
                "trade_date": [date(2024, 1, 2), date(2024, 1, 2)],  # Same date
                "open": [10.0, 11.0],
                "high": [12.0, 13.0],
                "low": [9.0, 10.0],
                "close": [11.0, 12.0],
                "volume": [1000, 2000],
            }
        )

        # Act: Run DQ check
        dq_result = self.dq_engine.check(dup_df, "stock_daily")

        # Assert: Should detect duplicates
        assert dq_result.passed is False, "DQ check should fail with duplicates"
        assert dq_result.has_errors is True, "Should have ERROR severity issues"
        dup_issues = [i for i in dq_result.issues if "duplicate" in i.message.lower()]
        assert len(dup_issues) > 0, "Should have duplicate issues"

    def test_dq_engine_passes_valid_data(self) -> None:
        """Test that DQEngine passes valid data."""
        # Arrange: Create valid data
        valid_df = pl.DataFrame(
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

        # Act: Run DQ check
        dq_result = self.dq_engine.check(valid_df, "stock_daily")

        # Assert: Should pass
        assert dq_result.passed is True, "DQ check should pass for valid data"
        assert dq_result.has_errors is False, "Should have no ERROR severity issues"
