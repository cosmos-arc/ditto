"""Tests for _apply_qfq_adj helper methods."""

from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory

import polars as pl
import pytest
from ditto_datahub.dq.engine import DQEngine
from ditto_datahub.repositories.bars import BarsRepository
from ditto_datahub.runtime.file_lock import FileLockManager
from ditto_datahub.runtime.sqlite_pool import SQLitePool
from ditto_datahub.stores.adj_factor_store import AdjFactorStore
from ditto_datahub.stores.bars_store import BarsStore
from ditto_datahub.stores.quarantine_store import QuarantineStore
from ditto_datahub.stores.security_store import SecurityStore
from ditto_datahub.stores.sqlite_client import SQLiteClient
from ditto_datahub.stores.stock_status_store import StockStatusStore


@pytest.fixture
def repo() -> BarsRepository:
    """Create a BarsRepository instance for testing."""
    temp_dir = TemporaryDirectory()
    data_root = Path(temp_dir.name)

    pool = SQLitePool(":memory:")
    pool.init_schema()
    client = SQLiteClient(pool)

    bars_store = BarsStore(data_root)
    adj_factor_store = AdjFactorStore(data_root)
    security_store = SecurityStore(client)
    stock_status_store = StockStatusStore(data_root)
    # Use empty DQEngine for testing (no config needed)
    dq_engine = DQEngine()
    lock_mgr = FileLockManager(data_root / ".locks")
    quarantine_store = QuarantineStore(data_root / "quarantine.db")

    repo = BarsRepository(
        bars_store,
        adj_factor_store,
        security_store,
        stock_status_store,
        dq_engine,
        lock_mgr,
        quarantine_store,
    )

    yield repo

    # Cleanup
    temp_dir.cleanup()


class TestParseAsOfDate:
    """Tests for _parse_asof_date method."""

    def test_parse_asof_date_with_string(self, repo: BarsRepository) -> None:
        """Test parsing asof date from ISO format string."""
        # Arrange
        asof_str = "2024-01-15"

        # Act
        result = repo._parse_asof_date(asof_str)

        # Assert
        assert result == date(2024, 1, 15)

    def test_parse_asof_date_with_date_object(self, repo: BarsRepository) -> None:
        """Test parsing asof date when already a date object."""
        # Arrange
        asof_date = date(2024, 1, 15)

        # Act
        result = repo._parse_asof_date(asof_date)

        # Assert
        assert result == date(2024, 1, 15)

    def test_parse_asof_date_with_different_string_formats(
        self, repo: BarsRepository
    ) -> None:
        """Test parsing asof date with various valid ISO format strings."""
        # Act & Assert
        assert repo._parse_asof_date("2024-01-15") == date(2024, 1, 15)
        assert repo._parse_asof_date("2024-12-31") == date(2024, 12, 31)
        assert repo._parse_asof_date("2020-02-29") == date(2020, 2, 29)  # Leap year


class TestFilterBaselineByAsOf:
    """Tests for _filter_baseline_by_asof method."""

    def test_filter_baseline_with_knowledge_date(self, repo: BarsRepository) -> None:
        """Test filtering baseline with knowledge_date column."""
        # Arrange
        adj_df = pl.DataFrame(
            {
                "sid": [1000001, 1000001, 1000001],
                "knowledge_date": [
                    date(2024, 1, 10),
                    date(2024, 1, 15),
                    date(2024, 1, 20),
                ],
                "trade_date": [
                    date(2024, 1, 10),
                    date(2024, 1, 15),
                    date(2024, 1, 20),
                ],
                "adj_factor": [1.0, 1.1, 1.2],
            }
        )
        pit_dt = date(2024, 1, 15)

        # Act
        result = repo._filter_baseline_by_asof(adj_df, pit_dt)

        # Assert: Should include rows with knowledge_date <= pit_dt
        assert len(result) == 2
        assert result["knowledge_date"].to_list() == [
            date(2024, 1, 10),
            date(2024, 1, 15),
        ]
        assert result["adj_factor"].to_list() == [1.0, 1.1]

    def test_filter_baseline_without_knowledge_date(
        self, repo: BarsRepository, mocker
    ) -> None:
        """Test filtering baseline without knowledge_date column.

        Fallback to trade_date when knowledge_date is missing.
        """
        # Arrange
        adj_df = pl.DataFrame(
            {
                "sid": [1000001, 1000001, 1000001],
                "trade_date": [
                    date(2024, 1, 10),
                    date(2024, 1, 15),
                    date(2024, 1, 20),
                ],
                "adj_factor": [1.0, 1.1, 1.2],
            }
        )
        pit_dt = date(2024, 1, 15)

        # Mock logger to verify warning is called
        mock_logger = mocker.patch("ditto_datahub.repositories.bars.logger")

        # Act
        result = repo._filter_baseline_by_asof(adj_df, pit_dt)

        # Assert: Should include rows with trade_date <= pit_dt
        assert len(result) == 2
        assert result["trade_date"].to_list() == [
            date(2024, 1, 10),
            date(2024, 1, 15),
        ]
        assert result["adj_factor"].to_list() == [1.0, 1.1]
        # Should log a warning about missing knowledge_date
        mock_logger.warning.assert_called_once()
        call_args = mock_logger.warning.call_args
        assert call_args is not None
        args, kwargs = call_args
        assert "knowledge_date" in args[0]
        assert kwargs["event"] == "bars_adj_missing_knowledge_date"

    def test_filter_baseline_multiple_sids(self, repo: BarsRepository) -> None:
        """Test filtering baseline with multiple SIDs."""
        # Arrange
        adj_df = pl.DataFrame(
            {
                "sid": [1000001, 1000001, 1000002, 1000002],
                "knowledge_date": [
                    date(2024, 1, 10),
                    date(2024, 1, 20),
                    date(2024, 1, 12),
                    date(2024, 1, 18),
                ],
                "adj_factor": [1.0, 1.1, 1.0, 1.05],
            }
        )
        pit_dt = date(2024, 1, 15)

        # Act
        result = repo._filter_baseline_by_asof(adj_df, pit_dt)

        # Assert: Should filter per-SID based on knowledge_date
        assert len(result) == 2
        assert result["sid"].to_list() == [1000001, 1000002]
        assert result["knowledge_date"].to_list() == [
            date(2024, 1, 10),
            date(2024, 1, 12),
        ]

    def test_filter_baseline_all_rows_before_asof(self, repo: BarsRepository) -> None:
        """Test filtering when all rows are before asof date."""
        # Arrange
        adj_df = pl.DataFrame(
            {
                "sid": [1000001, 1000001],
                "knowledge_date": [date(2024, 1, 10), date(2024, 1, 12)],
                "adj_factor": [1.0, 1.1],
            }
        )
        pit_dt = date(2024, 1, 20)

        # Act
        result = repo._filter_baseline_by_asof(adj_df, pit_dt)

        # Assert: Should return all rows
        assert len(result) == 2

    def test_filter_baseline_no_rows_before_asof(self, repo: BarsRepository) -> None:
        """Test filtering when no rows are before asof date."""
        # Arrange
        adj_df = pl.DataFrame(
            {
                "sid": [1000001, 1000001],
                "knowledge_date": [date(2024, 1, 20), date(2024, 1, 25)],
                "adj_factor": [1.0, 1.1],
            }
        )
        pit_dt = date(2024, 1, 15)

        # Act
        result = repo._filter_baseline_by_asof(adj_df, pit_dt)

        # Assert: Should return empty DataFrame
        assert len(result) == 0

    def test_filter_baseline_empty_dataframe(self, repo: BarsRepository) -> None:
        """Test filtering empty baseline DataFrame."""
        # Arrange
        adj_df = pl.DataFrame(
            schema={
                "sid": pl.Int64,
                "knowledge_date": pl.Date,
                "adj_factor": pl.Float64,
            }
        )
        pit_dt = date(2024, 1, 15)

        # Act
        result = repo._filter_baseline_by_asof(adj_df, pit_dt)

        # Assert: Should return empty DataFrame
        assert len(result) == 0
