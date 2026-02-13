"""Tests for Instrument ID allocator."""

from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from ditto_datahub.runtime.instrument_id_allocator import InstrumentIdAllocator
from ditto_infra.foundation import SQLitePool
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
        """Test allocating first ETF instrument_id returns 2M."""
        instrument_id = self.allocator.allocate("etf")

        assert instrument_id == 2_000_000

        # Verify it was persisted
        row = self.pool.execute(
            "SELECT current_max FROM instrument_id_sequence WHERE asset_class = ?",
            ["etf"],
        ).fetchone()
        assert row is not None
        assert row["current_max"] == 2_000_000

    def test_allocate_consecutive_etf_instrument_ids(self) -> None:
        """Test allocating consecutive ETF instrument IDs."""
        first_instrument_id = self.allocator.allocate("etf")
        second_instrument_id = self.allocator.allocate("etf")
        third_instrument_id = self.allocator.allocate("etf")

        assert first_instrument_id == 2_000_000
        assert second_instrument_id == 2_000_001
        assert third_instrument_id == 2_000_002

    def test_allocate_different_asset_classes(self) -> None:
        """Test allocating IDs for different asset classes."""
        etf_instrument_id = self.allocator.allocate("etf")
        stock_instrument_id = self.allocator.allocate("stock")
        index_instrument_id = self.allocator.allocate("index")

        assert etf_instrument_id == 2_000_000  # ETF range starts at 2M
        assert stock_instrument_id == 1_000_000  # Stock range starts at 1M
        assert index_instrument_id == 3_000_000  # Index range starts at 3M

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
        mock_logger = mocker.patch(
            "ditto_datahub.runtime.instrument_id_allocator.logger"
        )

        with pytest.raises(RuntimeError):
            self.allocator.allocate("stock")

        # Verify logger.error was called with error_type and error_message
        mock_logger.error.assert_called_once()
        call_kwargs = mock_logger.error.call_args.kwargs
        assert "error_type" in call_kwargs
        assert "error_message" in call_kwargs
        assert call_kwargs["event"] == "instrument_id_allocate"
        assert call_kwargs["error_type"] == "RuntimeError"
