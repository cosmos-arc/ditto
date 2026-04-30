"""Unit tests for CorporateActionsWriter."""

from datetime import date
from pathlib import Path

import polars as pl
import pytest
import pytest_mock
from ditto_data.storage.fundamental.corporate.corporate_actions_writer import (
    CorporateActionsWriter,
)
from ditto_data.storage.fundamental.specs import CORPORATE_ACTIONS_SPEC
from ditto_data.storage.sqlite_client import SQLiteClient
from ditto_platform.foundation import Metrics, SQLitePool

SPEC = CORPORATE_ACTIONS_SPEC


@pytest.fixture
def in_memory_db(tmp_path: Path) -> SQLitePool:
    """Provide in-memory SQLite database with corporate_actions table."""
    db_path = tmp_path / "test.db"

    pool = SQLitePool(str(db_path))
    pool.get_connection().execute(
        """CREATE TABLE IF NOT EXISTS corporate_actions (
        instrument_id INTEGER NOT NULL,
        action_type TEXT NOT NULL,
        action_date DATE NOT NULL,
        knowledge_date DATE NOT NULL,
        effective_from DATE NOT NULL,
        effective_to DATE,
        description TEXT,
        PRIMARY KEY (instrument_id, action_type, action_date, effective_from)
    )"""
    )
    return pool


@pytest.fixture
def corporate_actions_writer(in_memory_db: SQLitePool) -> CorporateActionsWriter:
    """Provide CorporateActionsWriter with in-memory database."""
    return CorporateActionsWriter(SPEC, SQLiteClient(in_memory_db))


@pytest.mark.unit
class TestCorporateActionsWriter:
    """Test cases for CorporateActionsWriter."""

    def test_write_success(
        self,
        corporate_actions_writer: CorporateActionsWriter,
        in_memory_db: SQLitePool,
        mocker: pytest_mock.MockFixture,
    ) -> None:
        """Test that write successfully inserts data."""
        # Arrange
        test_df = pl.DataFrame(
            {
                "instrument_id": [600000],
                "action_type": ["DIVIDEND"],
                "action_date": [date(2024, 5, 1)],
                "knowledge_date": [date(2024, 4, 25)],
                "effective_from": [date(2024, 4, 25)],
                "effective_to": [None],
                "description": ["Cash dividend 0.5 per share"],
            }
        )

        # Mock Metrics.data_records.add to avoid metric recording issues
        mock_metrics_add = mocker.patch.object(Metrics.data_records, "add")

        # Act
        count = corporate_actions_writer.write(test_df)

        # Assert
        assert count == 1
        mock_metrics_add.assert_called_once_with(
            1, {"dataset": "corporate_actions", "status": "success"}
        )

        # Verify data in database
        client = SQLiteClient(in_memory_db)
        rows = client.fetchall("SELECT * FROM corporate_actions")
        assert len(rows) == 1
        assert rows[0]["instrument_id"] == 600000
        assert rows[0]["action_type"] == "DIVIDEND"

    def test_write_returns_count(
        self,
        corporate_actions_writer: CorporateActionsWriter,
        in_memory_db: SQLitePool,
        mocker: pytest_mock.MockFixture,
    ) -> None:
        """Test that write returns correct record count."""
        # Arrange
        test_df = pl.DataFrame(
            {
                "instrument_id": [600000, 600001, 600002],
                "action_type": ["DIVIDEND", "SPLIT", "BUYBACK"],
                "action_date": [
                    date(2024, 5, 1),
                    date(2024, 6, 15),
                    date(2024, 7, 1),
                ],
                "knowledge_date": [
                    date(2024, 4, 25),
                    date(2024, 6, 10),
                    date(2024, 6, 25),
                ],
                "effective_from": [
                    date(2024, 4, 25),
                    date(2024, 6, 10),
                    date(2024, 6, 25),
                ],
                "effective_to": [None, None, None],
                "description": [
                    "Cash dividend",
                    "Stock split 2:1",
                    "Share buyback",
                ],
            }
        )

        mocker.patch.object(Metrics.data_records, "add")

        # Act
        count = corporate_actions_writer.write(test_df)

        # Assert
        assert count == 3

    def test_write_empty_dataframe(
        self,
        corporate_actions_writer: CorporateActionsWriter,
        in_memory_db: SQLitePool,
        mocker: pytest_mock.MockFixture,
    ) -> None:
        """Test that write handles empty DataFrame."""
        # Arrange
        test_df = pl.DataFrame(
            {
                "instrument_id": [],
                "action_type": [],
                "action_date": [],
                "knowledge_date": [],
                "effective_from": [],
                "effective_to": [],
                "description": [],
            }
        )

        mocker.patch.object(Metrics.data_records, "add")

        # Act
        count = corporate_actions_writer.write(test_df)

        # Assert
        assert count == 0

        # Verify no data in database
        client = SQLiteClient(in_memory_db)
        rows = client.fetchall("SELECT * FROM corporate_actions")
        assert len(rows) == 0

    def test_write_failure_rollback(
        self,
        corporate_actions_writer: CorporateActionsWriter,
        in_memory_db: SQLitePool,
        mocker: pytest_mock.MockFixture,
    ) -> None:
        """Test that write rolls back on failure."""
        # Arrange
        test_df = pl.DataFrame(
            {
                "instrument_id": [600000],
                "action_type": ["DIVIDEND"],
                "action_date": [date(2024, 5, 1)],
                "knowledge_date": [date(2024, 4, 25)],
                "effective_from": [date(2024, 4, 25)],
                "effective_to": [None],
                "description": ["Cash dividend 0.5 per share"],
            }
        )

        mocker.patch.object(Metrics.data_records, "add")

        # Force an error by using invalid data type
        # Create a mock client that raises RuntimeError
        mock_client = mocker.Mock(spec=SQLiteClient)
        mock_client.executemany.side_effect = RuntimeError("Database error")

        # Create writer with mock client
        mock_writer = CorporateActionsWriter(SPEC, mock_client)

        # Act & Assert
        with pytest.raises(RuntimeError, match="Database error"):
            mock_writer.write(test_df)

    def test_write_with_nullable_effective_to(
        self,
        corporate_actions_writer: CorporateActionsWriter,
        in_memory_db: SQLitePool,
        mocker: pytest_mock.MockFixture,
    ) -> None:
        """Test that write correctly handles nullable effective_to (current version)."""
        # Arrange
        test_df = pl.DataFrame(
            {
                "instrument_id": [600000],
                "action_type": ["DIVIDEND"],
                "action_date": [date(2024, 5, 1)],
                "knowledge_date": [date(2024, 4, 25)],
                "effective_from": [date(2024, 4, 25)],
                "effective_to": [None],
                "description": ["Cash dividend (current version)"],
            }
        )

        mocker.patch.object(Metrics.data_records, "add")

        # Act
        count = corporate_actions_writer.write(test_df)

        # Assert
        assert count == 1

        # Verify effective_to was written as NULL
        client = SQLiteClient(in_memory_db)
        rows = client.fetchall("SELECT * FROM corporate_actions")
        assert len(rows) == 1
        assert rows[0]["effective_to"] is None

    def test_write_multiple_actions_same_instrument(
        self,
        corporate_actions_writer: CorporateActionsWriter,
        in_memory_db: SQLitePool,
        mocker: pytest_mock.MockFixture,
    ) -> None:
        """Test that write handles multiple actions for same instrument."""
        # Arrange
        test_df = pl.DataFrame(
            {
                "instrument_id": [600000, 600000, 600000],
                "action_type": ["DIVIDEND", "SPLIT", "BUYBACK"],
                "action_date": [
                    date(2024, 5, 1),
                    date(2024, 6, 15),
                    date(2024, 7, 1),
                ],
                "knowledge_date": [
                    date(2024, 4, 25),
                    date(2024, 6, 10),
                    date(2024, 6, 25),
                ],
                "effective_from": [
                    date(2024, 4, 25),
                    date(2024, 6, 10),
                    date(2024, 6, 25),
                ],
                "effective_to": [None, None, None],
                "description": [
                    "Cash dividend",
                    "Stock split 2:1",
                    "Share buyback",
                ],
            }
        )

        mocker.patch.object(Metrics.data_records, "add")

        # Act
        count = corporate_actions_writer.write(test_df)

        # Assert
        assert count == 3

        # Verify all three actions were written
        client = SQLiteClient(in_memory_db)
        rows = client.fetchall(
            "SELECT * FROM corporate_actions WHERE instrument_id = ? "
            "ORDER BY action_date",
            [600000],
        )
        assert len(rows) == 3
        assert rows[0]["action_type"] == "DIVIDEND"
        assert rows[1]["action_type"] == "SPLIT"
        assert rows[2]["action_type"] == "BUYBACK"

    def test_write_on_conflict_do_nothing(
        self,
        corporate_actions_writer: CorporateActionsWriter,
        in_memory_db: SQLitePool,
        mocker: pytest_mock.MockFixture,
    ) -> None:
        """Test that write uses ON CONFLICT DO NOTHING correctly."""
        # Arrange
        test_df = pl.DataFrame(
            {
                "instrument_id": [600000],
                "action_type": ["DIVIDEND"],
                "action_date": [date(2024, 5, 1)],
                "knowledge_date": [date(2024, 4, 25)],
                "effective_from": [date(2024, 4, 25)],
                "effective_to": [None],
                "description": ["Cash dividend 0.5 per share"],
            }
        )

        mocker.patch.object(Metrics.data_records, "add")

        # Act - First write
        count1 = corporate_actions_writer.write(test_df)
        assert count1 == 1

        # Act - Second write with same data (should do nothing)
        count2 = corporate_actions_writer.write(test_df)
        assert count2 == 1  # SQLite reports 1 row inserted even with ON CONFLICT

        # Verify only one record exists
        client = SQLiteClient(in_memory_db)
        rows = client.fetchall("SELECT * FROM corporate_actions")
        assert len(rows) == 1
