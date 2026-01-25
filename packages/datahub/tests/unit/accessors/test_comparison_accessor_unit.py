"""Tests for ComparisonAccessor."""

from datetime import datetime

import polars as pl
import pytest
from ditto_datahub.accessors.comparison_accessor import ComparisonAccessor
from ditto_datahub.stores.quality.comparison_store import ComparisonStore


@pytest.mark.unit
class TestComparisonAccessor:
    """Tests for ComparisonAccessor."""

    def setup_method(self) -> None:
        """Set up test accessor."""
        import tempfile
        from pathlib import Path

        # Use temporary directory for testing
        self.temp_dir = tempfile.mkdtemp()
        self.store = ComparisonStore(base_path=Path(self.temp_dir))
        self.accessor = ComparisonAccessor(self.store)
        # Use recent date to avoid cleanup deletion
        self.recent_date = datetime.now().strftime("%Y%m%d")

    def teardown_method(self) -> None:
        """Clean up after test."""
        import shutil

        # Remove temporary directory
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_comparison_accessor_init(self) -> None:
        """Test ComparisonAccessor initialization."""
        assert self.accessor._comparison_store is not None

    def test_write_result(self) -> None:
        """Test writing comparison result."""
        import asyncio

        df = pl.DataFrame(
            {
                "dataset": ["stock_daily", "stock_daily"],
                "src_code": ["000001.SZ", "000002.SZ"],
                "trade_date": [self.recent_date, self.recent_date],
                "field": ["close", "close"],
            }
        )

        # Should not raise exception
        asyncio.run(self.accessor.write_result(self.recent_date, df, "stock_daily"))

    def test_read_result(self) -> None:
        """Test reading comparison result."""
        import asyncio

        df = pl.DataFrame(
            {
                "dataset": ["stock_daily"],
                "src_code": ["000001.SZ"],
                "trade_date": [self.recent_date],
                "field": ["close"],
            }
        )

        # Write first
        asyncio.run(self.accessor.write_result(self.recent_date, df, "stock_daily"))

        # Read back
        result = asyncio.run(self.accessor.read_result(self.recent_date, "stock_daily"))

        assert result is not None
        assert len(result) == 1

    def test_read_result_not_found(self) -> None:
        """Test reading non-existent result returns None."""
        import asyncio

        result = asyncio.run(self.accessor.read_result(self.recent_date, "stock_daily"))
        assert result is None

    def test_get_stats_empty(self) -> None:
        """Test get_stats when no data exists."""
        stats = self.accessor.get_stats()
        assert stats == []

    def test_get_stats_with_data(self) -> None:
        """Test get_stats with comparison data."""
        import asyncio

        df = pl.DataFrame(
            {
                "dataset": ["stock_daily", "stock_daily"],
                "src_code": ["000001.SZ", "000002.SZ"],
                "trade_date": [self.recent_date, self.recent_date],
                "field": ["close", "close"],
            }
        )

        # Write data
        asyncio.run(self.accessor.write_result(self.recent_date, df, "stock_daily"))

        # Get stats (synchronous method)
        stats = self.accessor.get_stats()

        assert len(stats) == 1
        assert stats[0]["trade_date"] == self.recent_date
        assert stats[0]["row_count"] == 2
