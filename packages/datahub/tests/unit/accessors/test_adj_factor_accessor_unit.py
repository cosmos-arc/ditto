"""Tests for AdjFactorAccessor."""

import shutil
import tempfile
from datetime import date
from pathlib import Path

import polars as pl
from ditto_datahub.accessors.adj_factor_accessor import AdjFactorAccessor
from ditto_datahub.models import OnDuplicate
from ditto_datahub.stores.adj_factor_store import AdjFactorStore
from ditto_foundation.concurrency import FileLockManager


class TestAdjFactorAccessor:
    """Tests for AdjFactorAccessor."""

    def setup_method(self) -> None:
        """Set up test environment."""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.adj_factor_store = AdjFactorStore(data_root=self.temp_dir)
        self.file_lock = FileLockManager(lock_dir=self.temp_dir / "locks")
        self.accessor = AdjFactorAccessor(
            adj_factor_store=self.adj_factor_store,
            file_lock=self.file_lock,
        )

    def test_write_with_file_lock(self) -> None:
        """Test write uses file lock for concurrent safety."""
        # Arrange
        df = pl.DataFrame(
            {
                "sid": [1000001, 1000002],
                "ts_code": ["600001.SH", "600002.SH"],
                "trade_date": [date(2024, 1, 2), date(2024, 1, 2)],
                "adj_factor": [1.1, 1.2],
            }
        )

        # Act
        write_result = self.accessor.write(
            dataset="adj_factor",
            df=df,
            year=2024,
            on_duplicate=OnDuplicate.ERROR,
        )

        # Assert
        assert write_result.file_path is not None
        assert write_result.checksum is not None
        assert len(write_result.checksum) > 0
        assert write_result.rows_written == 2
        assert write_result.rows_total == 2
        assert write_result.blocked is False

        # Verify data was written
        result = self.adj_factor_store.read(
            dataset="adj_factor",
            sids=None,
            start_date="2024-01-01",
            end_date="2024-01-31",
        )
        assert len(result) == 2

    def test_write_with_on_duplicate_keep_last(self) -> None:
        """Test write with KEEP_LAST strategy overwrites existing data."""
        # Arrange - Write initial data
        df1 = pl.DataFrame(
            {
                "sid": [1000001],
                "ts_code": ["600001.SH"],
                "trade_date": [date(2024, 1, 2)],
                "adj_factor": [1.1],
            }
        )

        self.accessor.write(
            dataset="adj_factor",
            df=df1,
            year=2024,
            on_duplicate=OnDuplicate.ERROR,
        )

        # Act - Write with updated factor
        df2 = pl.DataFrame(
            {
                "sid": [1000001],
                "ts_code": ["600001.SH"],
                "trade_date": [date(2024, 1, 2)],
                "adj_factor": [1.5],  # Updated value
            }
        )

        self.accessor.write(
            dataset="adj_factor",
            df=df2,
            year=2024,
            on_duplicate=OnDuplicate.KEEP_LAST,
        )

        # Assert - Verify new value was kept
        result = self.adj_factor_store.read(
            dataset="adj_factor",
            sids=[1000001],
            start_date="2024-01-01",
            end_date="2024-01-31",
        )
        assert len(result) == 1
        assert result["adj_factor"][0] == 1.5

    def teardown_method(self) -> None:
        """Clean up test environment."""
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)
