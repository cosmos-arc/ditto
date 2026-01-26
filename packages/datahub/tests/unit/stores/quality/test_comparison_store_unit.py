"""Tests for ComparisonStore."""

from datetime import datetime, timedelta

import polars as pl
import pytest
from ditto_datahub.stores.quality.comparison_store import ComparisonStore


@pytest.mark.unit
class TestComparisonStore:
    """Tests for ComparisonStore."""

    def setup_method(self) -> None:
        """Set up test store."""
        import tempfile

        # Use temporary directory for testing
        self.temp_dir = tempfile.mkdtemp()
        from pathlib import Path

        self.store = ComparisonStore(
            base_path=Path(self.temp_dir),
            retention_days=30,
        )

        # Use recent date to avoid cleanup deletion
        self.recent_date = datetime.now().strftime("%Y%m%d")

    def teardown_method(self) -> None:
        """Clean up after test."""
        import shutil

        # Remove temporary directory
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_comparison_store_init(self) -> None:
        """Test ComparisonStore initialization."""
        assert self.store.base_path.exists()
        assert self.store.retention_days == 30

    def test_write_comparison_basic(self) -> None:
        """Test writing comparison result."""
        df = pl.DataFrame(
            {
                "dataset": ["stock_daily", "stock_daily"],
                "src_code": ["000001.SZ", "000002.SZ"],
                "trade_date": [self.recent_date, self.recent_date],
                "field": ["close", "close"],
                "primary_value": [10.5, 20.3],
                "secondary_value": [10.5, 20.25],
                "diff": [0.0, 0.05],
            }
        )

        # Should not raise exception
        import asyncio

        asyncio.run(self.store.write_comparison(self.recent_date, df, "stock_daily"))

        # Verify file was created (路径包含 dataset)
        year = self.recent_date[:4]
        month = self.recent_date[4:6]
        expected_file = (
            self.store.base_path
            / f"year={year}"
            / f"month={month}"
            / "stock_daily"
            / f"{self.recent_date}.parquet"
        )
        assert expected_file.exists()

    def test_write_empty_dataframe(self) -> None:
        """Test writing empty DataFrame does nothing."""
        df = pl.DataFrame(
            schema={
                "src_code": pl.String(),
                "trade_date": pl.String(),
                "field": pl.String(),
            }
        )

        import asyncio

        # Should not raise or create file
        asyncio.run(self.store.write_comparison(self.recent_date, df, "stock_daily"))

        year = self.recent_date[:4]
        month = self.recent_date[4:6]
        expected_file = (
            self.store.base_path
            / f"year={year}"
            / f"month={month}"
            / "stock_daily"
            / f"{self.recent_date}.parquet"
        )
        assert not expected_file.exists()

    def test_read_comparison_existing(self) -> None:
        """Test reading existing comparison result."""
        df = pl.DataFrame(
            {
                "dataset": ["stock_daily", "stock_daily"],
                "src_code": ["000001.SZ", "000002.SZ"],
                "trade_date": [self.recent_date, self.recent_date],
                "field": ["close", "close"],
            }
        )

        import asyncio

        # Write first
        asyncio.run(self.store.write_comparison(self.recent_date, df, "stock_daily"))

        # Read back
        result = asyncio.run(
            self.store.read_comparison(self.recent_date, "stock_daily")
        )

        assert result is not None
        assert len(result) == 2
        assert result["dataset"].unique().to_list() == ["stock_daily"]

    def test_read_comparison_not_found(self) -> None:
        """Test reading non-existent comparison returns None."""
        import asyncio

        result = asyncio.run(
            self.store.read_comparison(self.recent_date, "stock_daily")
        )

        assert result is None

    def test_read_comparison_filters_by_dataset(self) -> None:
        """Test reading filters by dataset (每个 dataset 独立文件)."""
        stock_df = pl.DataFrame(
            {
                "dataset": ["stock_daily", "stock_daily"],
                "src_code": ["000001.SZ", "000002.SZ"],
                "trade_date": [self.recent_date, self.recent_date],
                "field": ["close", "close"],
            }
        )

        index_df = pl.DataFrame(
            {
                "dataset": ["index_daily", "index_daily"],
                "src_code": ["000001.SH", "000999.SH"],
                "trade_date": [self.recent_date, self.recent_date],
                "field": ["close", "close"],
            }
        )

        import asyncio

        # 写入两个不同 dataset（会写入不同文件）
        asyncio.run(
            self.store.write_comparison(self.recent_date, stock_df, "stock_daily")
        )
        asyncio.run(
            self.store.write_comparison(self.recent_date, index_df, "index_daily")
        )

        # Read only stock_daily
        result = asyncio.run(
            self.store.read_comparison(self.recent_date, "stock_daily")
        )

        assert result is not None
        assert len(result) == 2
        assert result["dataset"].unique().to_list() == ["stock_daily"]

        # Read only index_daily
        result = asyncio.run(
            self.store.read_comparison(self.recent_date, "index_daily")
        )

        assert result is not None
        assert len(result) == 2
        assert result["dataset"].unique().to_list() == ["index_daily"]

    def test_cleanup_old_data(self) -> None:
        """Test automatic cleanup of old data."""
        # Create old file (simulate old date)
        old_date = (datetime.now() - timedelta(days=35)).strftime("%Y%m%d")
        old_df = pl.DataFrame(
            {
                "dataset": ["stock_daily"],
                "src_code": ["000001.SZ"],
                "trade_date": [old_date],
            }
        )

        # Create recent file
        recent_df = pl.DataFrame(
            {
                "dataset": ["stock_daily"],
                "src_code": ["000001.SZ"],
                "trade_date": [self.recent_date],
            }
        )

        import asyncio

        asyncio.run(self.store.write_comparison(old_date, old_df, "stock_daily"))
        asyncio.run(
            self.store.write_comparison(self.recent_date, recent_df, "stock_daily")
        )

        # Trigger cleanup by writing new data
        # Create a second recent date to avoid cleanup
        recent_date2 = (datetime.now() - timedelta(days=1)).strftime("%Y%m%d")
        asyncio.run(self.store.write_comparison(recent_date2, recent_df, "stock_daily"))

        # Old file should be removed, recent file should exist
        old_year = old_date[:4]
        old_month = old_date[4:6]
        old_file_path = (
            self.store.base_path
            / f"year={old_year}"
            / f"month={old_month}"
            / "stock_daily"
            / f"{old_date}.parquet"
        )

        recent_year = self.recent_date[:4]
        recent_month = self.recent_date[4:6]
        recent_file = (
            self.store.base_path
            / f"year={recent_year}"
            / f"month={recent_month}"
            / "stock_daily"
            / f"{self.recent_date}.parquet"
        )

        # Old file should be deleted, recent file should exist
        assert not old_file_path.exists()
        assert recent_file.exists()
