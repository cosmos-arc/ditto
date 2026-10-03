"""Tests for Instrument ID allocator."""

from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from ditto_data.runtime.instrument_id_allocator import InstrumentIdAllocator
from ditto_platform.foundation import SQLitePool
from pytest_mock import MockerFixture


@pytest.mark.integration
class TestInstrumentIdAllocator:
    """Test cases for InstrumentIdAllocator."""

    def setup_method(self) -> None:
        """Set up test environment."""
        self.temp_dir = TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test.db"

        # Initialize test database
        self.pool = SQLitePool(str(self.db_path))
        self.allocator = InstrumentIdAllocator(self.pool)

        # Create instrument_id_sequence table
        self.pool.execute("""
            CREATE TABLE IF NOT EXISTS instrument_id_sequence (
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

    def test_allocate_first_etf_instrument_id(self) -> None:
        """无种子行时首个 ETF 分配 = min_id + 1（min_id 保留）。"""
        instrument_id = self.allocator.allocate("etf")

        assert instrument_id == 2_000_001

        # Verify it was persisted
        row = self.pool.execute(
            "SELECT current_max FROM instrument_id_sequence WHERE asset_class = ?",
            ["etf"],
        ).fetchone()
        assert row is not None
        assert row["current_max"] == 2_000_001

    def test_seeded_sequence_first_allocation_matches_unseeded(
        self,
    ) -> None:
        """种子（current_max = min_id）后的首笔分配与无种子首笔分配同语义。"""
        self.pool.execute("BEGIN IMMEDIATE")
        self.pool.execute(
            "INSERT OR REPLACE INTO instrument_id_sequence VALUES (?, ?)",
            ["etf", 2_000_000],
        )
        self.pool.commit()

        assert self.allocator.allocate("etf") == 2_000_001

    def test_allocate_consecutive_etf_instrument_ids(self) -> None:
        """Test allocating consecutive ETF instrument IDs."""
        first_instrument_id = self.allocator.allocate("etf")
        second_instrument_id = self.allocator.allocate("etf")
        third_instrument_id = self.allocator.allocate("etf")

        assert first_instrument_id == 2_000_001
        assert second_instrument_id == 2_000_002
        assert third_instrument_id == 2_000_003

    def test_allocate_different_asset_classes(self) -> None:
        """Test allocating IDs for different asset classes."""
        etf_instrument_id = self.allocator.allocate("etf")
        stock_instrument_id = self.allocator.allocate("stock")
        index_instrument_id = self.allocator.allocate("index")

        assert etf_instrument_id == 2_000_001  # ETF range starts at 2M + 1
        assert stock_instrument_id == 1_000_001  # Stock range starts at 1M + 1
        assert index_instrument_id == 3_000_001  # Index range starts at 3M + 1

    def test_instrument_id_exhaustion(self) -> None:
        """Test behavior when instrument_id range is exhausted."""
        # Set current_max to near the limit
        self.pool.execute("BEGIN IMMEDIATE")
        self.pool.execute(
            "INSERT OR REPLACE INTO instrument_id_sequence VALUES (?, ?)",
            ["etf", 2_999_999],
        )
        self.pool.commit()

        with pytest.raises(OverflowError, match="Instrument ID exhausted for etf"):
            self.allocator.allocate("etf")

    def test_unknown_asset_class(self) -> None:
        """Test allocating instrument_id for unknown asset class."""
        with pytest.raises(ValueError, match="Unknown asset class"):
            self.allocator.allocate("unknown")

    def test_allocate_logs_error_on_exception(self, mocker: MockerFixture) -> None:
        """Test allocate logs error with error_type and error_message on exception."""
        # Mock pool.execute to raise an exception during transaction
        mocker.patch.object(
            self.pool, "execute", side_effect=RuntimeError("Connection lost")
        )
        mock_logger = mocker.patch("ditto_data.runtime.instrument_id_allocator.logger")

        with pytest.raises(RuntimeError):
            self.allocator.allocate("stock")

        # Verify logger.error was called with error_type and error_message
        mock_logger.error.assert_called_once()
        call_kwargs = mock_logger.error.call_args.kwargs
        assert "error_type" in call_kwargs
        assert "error_message" in call_kwargs
        assert call_kwargs["event"] == "instrument_id_allocate"
        assert call_kwargs["error_type"] == "RuntimeError"
