"""Tests for SID Allocator."""

from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from ditto_datahub.runtime.sid_allocator import SidAllocator
from ditto_datahub.runtime.sqlite_pool import SQLitePool


class TestSidAllocator:
    """Test cases for SidAllocator."""

    def setup_method(self) -> None:
        """Set up test environment."""
        self.temp_dir = TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test.db"

        # Initialize test database
        self.pool = SQLitePool(str(self.db_path))
        self.allocator = SidAllocator(self.pool)

        # Create sid_sequence table
        self.pool.execute("""
            CREATE TABLE IF NOT EXISTS sid_sequence (
                asset_class TEXT PRIMARY KEY,
                current_max INTEGER NOT NULL
            )
        """)

    def teardown_method(self) -> None:
        """Clean up test environment."""
        try:
            self.pool.execute("COMMIT")
        except Exception:
            pass
        self.pool.close()
        self.temp_dir.cleanup()

    def test_allocate_first_etf_sid(self) -> None:
        """Test allocating first ETF SID returns 2M."""
        sid = self.allocator.allocate("etf")

        assert sid == 2_000_000

        # Verify it was persisted
        row = self.pool.execute(
            "SELECT current_max FROM sid_sequence WHERE asset_class = ?", ["etf"]
        ).fetchone()
        assert row is not None
        assert row["current_max"] == 2_000_000

    def test_allocate_consecutive_etf_sids(self) -> None:
        """Test allocating consecutive ETF SIDs."""
        first_sid = self.allocator.allocate("etf")
        second_sid = self.allocator.allocate("etf")
        third_sid = self.allocator.allocate("etf")

        assert first_sid == 2_000_000
        assert second_sid == 2_000_001
        assert third_sid == 2_000_002

    def test_allocate_different_asset_classes(self) -> None:
        """Test allocating SIDs for different asset classes."""
        etf_sid = self.allocator.allocate("etf")
        stock_sid = self.allocator.allocate("stock")
        index_sid = self.allocator.allocate("index")

        assert etf_sid == 2_000_000  # ETF range starts at 2M
        assert stock_sid == 1_000_000  # Stock range starts at 1M
        assert index_sid == 3_000_000  # Index range starts at 3M

    def test_sid_exhaustion(self) -> None:
        """Test behavior when SID range is exhausted."""
        # Set current_max to near the limit
        self.pool.execute("BEGIN IMMEDIATE")
        self.pool.execute(
            "INSERT OR REPLACE INTO sid_sequence VALUES (?, ?)", ["etf", 2_999_999]
        )
        self.pool.commit()

        with pytest.raises(OverflowError, match="SID exhausted for etf"):
            self.allocator.allocate("etf")

    def test_unknown_asset_class(self) -> None:
        """Test allocating SID for unknown asset class."""
        with pytest.raises(ValueError, match="Unknown asset class"):
            self.allocator.allocate("unknown")
