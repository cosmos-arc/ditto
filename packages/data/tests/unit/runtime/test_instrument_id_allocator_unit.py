"""Unit tests for InstrumentIdAllocator."""

import pytest
from ditto_data.models.common import InstrumentIdRange
from ditto_data.runtime.instrument_id_allocator import InstrumentIdAllocator
from pytest_mock import MockerFixture


@pytest.mark.unit
class TestInstrumentIdAllocator:
    """Tests for InstrumentIdAllocator."""

    def test_initialization(self, mocker: MockerFixture) -> None:
        """Test that InstrumentIdAllocator initializes with SQLite pool."""
        mock_pool = mocker.Mock()
        allocator = InstrumentIdAllocator(mock_pool)
        assert allocator._pool is mock_pool

    def test_allocate_stock_id_first_allocation(self, mocker: MockerFixture) -> None:
        """Test allocating first stock ID starts at min range."""
        mock_pool = mocker.Mock()
        # No existing record
        mock_pool.execute.return_value.fetchone.return_value = None

        allocator = InstrumentIdAllocator(mock_pool)
        instrument_id = allocator.allocate("stock")

        # Should start at stock min_id (1,000,000)
        assert instrument_id == 1_000_000
        # Verify insert was called
        mock_pool.execute.assert_any_call(
            "INSERT INTO instrument_id_sequence "
            + "(asset_class, current_max) VALUES (?, ?)",
            ["stock", 1_000_000],
        )
        mock_pool.commit.assert_called_once()

    def test_allocate_etf_id_first_allocation(self, mocker: MockerFixture) -> None:
        """Test allocating first ETF ID starts at min range."""
        mock_pool = mocker.Mock()
        mock_pool.execute.return_value.fetchone.return_value = None

        allocator = InstrumentIdAllocator(mock_pool)
        instrument_id = allocator.allocate("etf")

        # Should start at etf min_id (2,000,000)
        assert instrument_id == 2_000_000
        mock_pool.execute.assert_any_call(
            "INSERT INTO instrument_id_sequence "
            + "(asset_class, current_max) VALUES (?, ?)",
            ["etf", 2_000_000],
        )

    def test_allocate_index_id_first_allocation(self, mocker: MockerFixture) -> None:
        """Test allocating first index ID starts at min range."""
        mock_pool = mocker.Mock()
        mock_pool.execute.return_value.fetchone.return_value = None

        allocator = InstrumentIdAllocator(mock_pool)
        instrument_id = allocator.allocate("index")

        # Should start at index min_id (3,000,000)
        assert instrument_id == 3_000_000
        mock_pool.execute.assert_any_call(
            "INSERT INTO instrument_id_sequence "
            + "(asset_class, current_max) VALUES (?, ?)",
            ["index", 3_000_000],
        )

    def test_allocate_increments_existing_id(self, mocker: MockerFixture) -> None:
        """Test that allocation increments existing ID."""
        mock_pool = mocker.Mock()
        # Existing record with current_max = 1,000,005
        mock_pool.execute.return_value.fetchone.return_value = {
            "current_max": 1_000_005
        }

        allocator = InstrumentIdAllocator(mock_pool)
        instrument_id = allocator.allocate("stock")

        # Should increment to 1,000,006
        assert instrument_id == 1_000_006
        mock_pool.execute.assert_any_call(
            "UPDATE instrument_id_sequence "
            + "SET current_max = ? WHERE asset_class = ?",
            [1_000_006, "stock"],
        )

    def test_allocate_is_deterministic_sequential(self, mocker: MockerFixture) -> None:
        """Test that allocations are sequential and deterministic."""
        mock_pool = mocker.Mock()

        # First allocation returns None (no existing record)
        mock_pool.execute.return_value.fetchone.side_effect = [
            None,  # First call
            {"current_max": 1_000_000},  # After first insert, second call sees it
        ]

        allocator = InstrumentIdAllocator(mock_pool)

        id1 = allocator.allocate("stock")
        assert id1 == 1_000_000

        # Reset mock for next call
        mock_pool.reset_mock()
        mock_pool.execute.return_value.fetchone.return_value = {
            "current_max": 1_000_000
        }

        instrument_id2 = allocator.allocate("stock")
        assert instrument_id2 == 1_000_001

        # Verify UPDATE was called with incremented value
        mock_pool.execute.assert_any_call(
            "UPDATE instrument_id_sequence "
            + "SET current_max = ? WHERE asset_class = ?",
            [1_000_001, "stock"],
        )

    def test_allocate_raises_overflow_when_exhausted(
        self, mocker: MockerFixture
    ) -> None:
        """Test that allocation raises OverflowError when range exhausted."""
        mock_pool = mocker.Mock()
        # Return current_max at max range
        mock_pool.execute.return_value.fetchone.return_value = {
            "current_max": 1_999_999
        }

        allocator = InstrumentIdAllocator(mock_pool)

        with pytest.raises(OverflowError) as exc_info:
            allocator.allocate("stock")

        assert "Instrument ID exhausted for stock" in str(exc_info.value)
        mock_pool.rollback.assert_called_once()

    def test_allocate_begins_transaction(self, mocker: MockerFixture) -> None:
        """Test that allocation uses BEGIN IMMEDIATE."""
        mock_pool = mocker.Mock()
        mock_pool.execute.return_value.fetchone.return_value = None

        allocator = InstrumentIdAllocator(mock_pool)
        allocator.allocate("stock")

        # Check that BEGIN IMMEDIATE was called
        mock_pool.execute.assert_any_call("BEGIN IMMEDIATE")

    def test_allocate_commits_on_success(self, mocker: MockerFixture) -> None:
        """Test that allocation commits on success."""
        mock_pool = mocker.Mock()
        mock_pool.execute.return_value.fetchone.return_value = None

        allocator = InstrumentIdAllocator(mock_pool)
        allocator.allocate("stock")

        mock_pool.commit.assert_called_once()

    def test_allocate_rolls_back_on_error(self, mocker: MockerFixture) -> None:
        """Test that allocation rolls back on any error."""
        mock_pool = mocker.Mock()
        # Simulate database error
        mock_pool.execute.side_effect = RuntimeError("Database error")

        allocator = InstrumentIdAllocator(mock_pool)

        with pytest.raises(RuntimeError):
            allocator.allocate("stock")

        mock_pool.rollback.assert_called_once()

    def test_allocate_uses_correct_range_for_asset_class(self) -> None:
        """Test that allocation uses correct range for each asset class."""
        # Verify ranges from InstrumentIdRange
        stock_range = InstrumentIdRange.get_range("stock")
        etf_range = InstrumentIdRange.get_range("etf")
        index_range = InstrumentIdRange.get_range("index")

        assert stock_range.min_id == 1_000_000
        assert stock_range.max_id == 1_999_999

        assert etf_range.min_id == 2_000_000
        assert etf_range.max_id == 2_999_999

        assert index_range.min_id == 3_000_000
        assert index_range.max_id == 3_999_999
