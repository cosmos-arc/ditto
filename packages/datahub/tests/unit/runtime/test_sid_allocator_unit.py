"""Unit tests for SidAllocator."""

import pytest
from ditto_datahub.models.common import AssetSidRange
from ditto_datahub.runtime.sid_allocator import SidAllocator
from pytest_mock import MockerFixture


@pytest.mark.unit
class TestSidAllocator:
    """Tests for SidAllocator."""

    def test_initialization(self, mocker: MockerFixture) -> None:
        """Test that SidAllocator initializes with SQLite pool."""
        mock_pool = mocker.Mock()
        allocator = SidAllocator(mock_pool)
        assert allocator._pool is mock_pool

    def test_allocate_stock_sid_first_allocation(self, mocker: MockerFixture) -> None:
        """Test allocating first stock SID starts at min range."""
        mock_pool = mocker.Mock()
        # No existing record
        mock_pool.execute.return_value.fetchone.return_value = None

        allocator = SidAllocator(mock_pool)
        sid = allocator.allocate("stock")

        # Should start at stock min_sid (1,000,000)
        assert sid == 1_000_000
        # Verify insert was called
        mock_pool.execute.assert_any_call(
            "INSERT INTO sid_sequence (asset_class, current_max) VALUES (?, ?)",
            ["stock", 1_000_000],
        )
        mock_pool.commit.assert_called_once()

    def test_allocate_etf_sid_first_allocation(self, mocker: MockerFixture) -> None:
        """Test allocating first ETF SID starts at min range."""
        mock_pool = mocker.Mock()
        mock_pool.execute.return_value.fetchone.return_value = None

        allocator = SidAllocator(mock_pool)
        sid = allocator.allocate("etf")

        # Should start at etf min_sid (2,000,000)
        assert sid == 2_000_000
        mock_pool.execute.assert_any_call(
            "INSERT INTO sid_sequence (asset_class, current_max) VALUES (?, ?)",
            ["etf", 2_000_000],
        )

    def test_allocate_index_sid_first_allocation(self, mocker: MockerFixture) -> None:
        """Test allocating first index SID starts at min range."""
        mock_pool = mocker.Mock()
        mock_pool.execute.return_value.fetchone.return_value = None

        allocator = SidAllocator(mock_pool)
        sid = allocator.allocate("index")

        # Should start at index min_sid (3,000,000)
        assert sid == 3_000_000
        mock_pool.execute.assert_any_call(
            "INSERT INTO sid_sequence (asset_class, current_max) VALUES (?, ?)",
            ["index", 3_000_000],
        )

    def test_allocate_increments_existing_sid(self, mocker: MockerFixture) -> None:
        """Test that allocation increments existing SID."""
        mock_pool = mocker.Mock()
        # Existing record with current_max = 1,000,005
        mock_pool.execute.return_value.fetchone.return_value = {
            "current_max": 1_000_005
        }

        allocator = SidAllocator(mock_pool)
        sid = allocator.allocate("stock")

        # Should increment to 1,000,006
        assert sid == 1_000_006
        mock_pool.execute.assert_any_call(
            "UPDATE sid_sequence SET current_max = ? WHERE asset_class = ?",
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

        allocator = SidAllocator(mock_pool)

        sid1 = allocator.allocate("stock")
        assert sid1 == 1_000_000

        # Reset mock for next call
        mock_pool.reset_mock()
        mock_pool.execute.return_value.fetchone.return_value = {
            "current_max": 1_000_000
        }

        sid2 = allocator.allocate("stock")
        assert sid2 == 1_000_001

        # Verify UPDATE was called with incremented value
        mock_pool.execute.assert_any_call(
            "UPDATE sid_sequence SET current_max = ? WHERE asset_class = ?",
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

        allocator = SidAllocator(mock_pool)

        with pytest.raises(OverflowError) as exc_info:
            allocator.allocate("stock")

        assert "SID exhausted for stock" in str(exc_info.value)
        mock_pool.rollback.assert_called_once()

    def test_allocate_begins_transaction(self, mocker: MockerFixture) -> None:
        """Test that allocation uses BEGIN IMMEDIATE."""
        mock_pool = mocker.Mock()
        mock_pool.execute.return_value.fetchone.return_value = None

        allocator = SidAllocator(mock_pool)
        allocator.allocate("stock")

        # Check that BEGIN IMMEDIATE was called
        mock_pool.execute.assert_any_call("BEGIN IMMEDIATE")

    def test_allocate_commits_on_success(self, mocker: MockerFixture) -> None:
        """Test that allocation commits on success."""
        mock_pool = mocker.Mock()
        mock_pool.execute.return_value.fetchone.return_value = None

        allocator = SidAllocator(mock_pool)
        allocator.allocate("stock")

        mock_pool.commit.assert_called_once()

    def test_allocate_rolls_back_on_error(self, mocker: MockerFixture) -> None:
        """Test that allocation rolls back on any error."""
        mock_pool = mocker.Mock()
        # Simulate database error
        mock_pool.execute.side_effect = RuntimeError("Database error")

        allocator = SidAllocator(mock_pool)

        with pytest.raises(RuntimeError):
            allocator.allocate("stock")

        mock_pool.rollback.assert_called_once()

    def test_allocate_uses_correct_range_for_asset_class(self) -> None:
        """Test that allocation uses correct range for each asset class."""
        # Verify ranges from AssetSidRange
        stock_range = AssetSidRange.get_range("stock")
        etf_range = AssetSidRange.get_range("etf")
        index_range = AssetSidRange.get_range("index")

        assert stock_range.min_sid == 1_000_000
        assert stock_range.max_sid == 1_999_999

        assert etf_range.min_sid == 2_000_000
        assert etf_range.max_sid == 2_999_999

        assert index_range.min_sid == 3_000_000
        assert index_range.max_sid == 3_999_999
