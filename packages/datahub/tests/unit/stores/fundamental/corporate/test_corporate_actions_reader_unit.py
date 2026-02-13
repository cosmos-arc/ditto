"""Unit tests for CorporateActionsReader."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import polars as pl
import pytest
from ditto_datahub.stores.fundamental.corporate.corporate_actions_reader import (
    CorporateActionsReader,
)
from ditto_datahub.stores.sqlite_client import SQLiteClient
from ditto_infra.foundation import SQLitePool


@pytest.fixture
def in_memory_db(tmp_path: Path) -> SQLitePool:
    """Provide in-memory SQLite database with corporate_actions table."""
    db_path = tmp_path / "test.db"

    pool = SQLitePool(str(db_path))
    pool.get_connection().execute(
        """CREATE TABLE IF NOT EXISTS corporate_actions (
        instrument_id TEXT NOT NULL,
        action_type TEXT NOT NULL,
        announcement_date DATE NOT NULL,
        effective_date DATE,
        description TEXT,
        PRIMARY KEY (instrument_id, action_type, announcement_date)
    )"""
    )
    return pool


@pytest.fixture
def corporate_actions_reader(in_memory_db: SQLitePool) -> CorporateActionsReader:
    """Provide CorporateActionsReader with in-memory database."""
    return CorporateActionsReader(SQLiteClient(in_memory_db))


@pytest.mark.unit
class TestCorporateActionsReader:
    """Test cases for CorporateActionsReader."""

    def test_get_returns_data(
        self,
        corporate_actions_reader: CorporateActionsReader,
        in_memory_db: SQLitePool,
    ) -> None:
        """Test that get returns data for valid query."""
        # Arrange
        client = SQLiteClient(in_memory_db)
        client.execute(
            """INSERT INTO corporate_actions
            (instrument_id, action_type, announcement_date,
             effective_date, description)
            VALUES (?, ?, ?, ?, ?)""",
            [
                "600000",
                "DIVIDEND",
                date(2024, 5, 1),
                date(2024, 6, 1),
                "Cash dividend 0.5 per share",
            ],
        )
        client.commit()

        # Act
        result = corporate_actions_reader.get("600000")

        # Assert
        assert len(result) == 1
        assert result["instrument_id"][0] == "600000"
        assert result["action_type"][0] == "DIVIDEND"
        # SQLite returns dates as strings
        assert result["announcement_date"][0] == "2024-05-01"
        assert result["effective_date"][0] == "2024-06-01"
        assert result["description"][0] == "Cash dividend 0.5 per share"

    def test_get_empty_table(
        self,
        corporate_actions_reader: CorporateActionsReader,
    ) -> None:
        """Test that get returns empty DataFrame for empty table."""
        # Act
        result = corporate_actions_reader.get("600000")

        # Assert
        assert len(result) == 0
        assert isinstance(result, pl.DataFrame)

    def test_get_no_data(
        self,
        corporate_actions_reader: CorporateActionsReader,
        in_memory_db: SQLitePool,
    ) -> None:
        """Test that get returns empty DataFrame for non-existent instrument."""
        # Arrange
        client = SQLiteClient(in_memory_db)
        client.execute(
            """INSERT INTO corporate_actions
            (instrument_id, action_type, announcement_date,
             effective_date, description)
            VALUES (?, ?, ?, ?, ?)""",
            [
                "600001",
                "DIVIDEND",
                date(2024, 5, 1),
                date(2024, 6, 1),
                "Cash dividend 0.5 per share",
            ],
        )
        client.commit()

        # Act
        result = corporate_actions_reader.get("600000")

        # Assert
        assert len(result) == 0

    def test_get_with_start_date(
        self,
        corporate_actions_reader: CorporateActionsReader,
        in_memory_db: SQLitePool,
    ) -> None:
        """Test that get filters by start_date correctly."""
        # Arrange
        client = SQLiteClient(in_memory_db)
        client.execute(
            """INSERT INTO corporate_actions
            (instrument_id, action_type, announcement_date,
             effective_date, description)
            VALUES (?, ?, ?, ?, ?)""",
            [
                "600000",
                "DIVIDEND",
                date(2024, 4, 1),
                date(2024, 5, 1),
                "April dividend",
            ],
        )
        client.execute(
            """INSERT INTO corporate_actions
            (instrument_id, action_type, announcement_date,
             effective_date, description)
            VALUES (?, ?, ?, ?, ?)""",
            [
                "600000",
                "SPLIT",
                date(2024, 5, 15),
                date(2024, 6, 1),
                "Stock split 2:1",
            ],
        )
        client.commit()

        # Act - Query from May 1st onwards
        result = corporate_actions_reader.get("600000", start_date=date(2024, 5, 1))

        # Assert - Should only include the split (announcement_date >= 2024-05-01)
        assert len(result) == 1
        assert result["action_type"][0] == "SPLIT"

    def test_get_with_end_date(
        self,
        corporate_actions_reader: CorporateActionsReader,
        in_memory_db: SQLitePool,
    ) -> None:
        """Test that get filters by end_date correctly."""
        # Arrange
        client = SQLiteClient(in_memory_db)
        client.execute(
            """INSERT INTO corporate_actions
            (instrument_id, action_type, announcement_date,
             effective_date, description)
            VALUES (?, ?, ?, ?, ?)""",
            [
                "600000",
                "DIVIDEND",
                date(2024, 4, 1),
                date(2024, 5, 1),
                "April dividend",
            ],
        )
        client.execute(
            """INSERT INTO corporate_actions
            (instrument_id, action_type, announcement_date,
             effective_date, description)
            VALUES (?, ?, ?, ?, ?)""",
            [
                "600000",
                "SPLIT",
                date(2024, 5, 15),
                date(2024, 6, 1),
                "Stock split 2:1",
            ],
        )
        client.commit()

        # Act - Query up to May 1st
        result = corporate_actions_reader.get("600000", end_date=date(2024, 5, 1))

        # Assert - Should only include the dividend (announcement_date <= 2024-05-01)
        assert len(result) == 1
        assert result["action_type"][0] == "DIVIDEND"

    def test_get_with_date_range(
        self,
        corporate_actions_reader: CorporateActionsReader,
        in_memory_db: SQLitePool,
    ) -> None:
        """Test that get filters by both start_date and end_date correctly."""
        # Arrange
        client = SQLiteClient(in_memory_db)
        client.execute(
            """INSERT INTO corporate_actions
            (instrument_id, action_type, announcement_date,
             effective_date, description)
            VALUES (?, ?, ?, ?, ?)""",
            [
                "600000",
                "DIVIDEND",
                date(2024, 3, 1),
                date(2024, 4, 1),
                "March dividend",
            ],
        )
        client.execute(
            """INSERT INTO corporate_actions
            (instrument_id, action_type, announcement_date,
             effective_date, description)
            VALUES (?, ?, ?, ?, ?)""",
            [
                "600000",
                "SPLIT",
                date(2024, 4, 15),
                date(2024, 5, 1),
                "Stock split 2:1",
            ],
        )
        client.execute(
            """INSERT INTO corporate_actions
            (instrument_id, action_type, announcement_date,
             effective_date, description)
            VALUES (?, ?, ?, ?, ?)""",
            [
                "600000",
                "BUYBACK",
                date(2024, 5, 15),
                date(2024, 6, 1),
                "Share buyback",
            ],
        )
        client.commit()

        # Act - Query from April 1st to April 30th
        result = corporate_actions_reader.get(
            "600000",
            start_date=date(2024, 4, 1),
            end_date=date(2024, 4, 30),
        )

        # Assert - Should only include the split (announcement_date in range)
        assert len(result) == 1
        assert result["action_type"][0] == "SPLIT"

    def test_get_multiple_actions(
        self,
        corporate_actions_reader: CorporateActionsReader,
        in_memory_db: SQLitePool,
    ) -> None:
        """Test that get returns multiple corporate actions ordered by date."""
        # Arrange
        client = SQLiteClient(in_memory_db)
        client.execute(
            """INSERT INTO corporate_actions
            (instrument_id, action_type, announcement_date,
             effective_date, description)
            VALUES (?, ?, ?, ?, ?)""",
            [
                "600000",
                "DIVIDEND",
                date(2024, 5, 1),
                date(2024, 6, 1),
                "May dividend",
            ],
        )
        client.execute(
            """INSERT INTO corporate_actions
            (instrument_id, action_type, announcement_date,
             effective_date, description)
            VALUES (?, ?, ?, ?, ?)""",
            [
                "600000",
                "SPLIT",
                date(2024, 6, 15),
                date(2024, 7, 1),
                "Stock split 2:1",
            ],
        )
        client.execute(
            """INSERT INTO corporate_actions
            (instrument_id, action_type, announcement_date,
             effective_date, description)
            VALUES (?, ?, ?, ?, ?)""",
            [
                "600000",
                "BUYBACK",
                date(2024, 4, 1),
                date(2024, 5, 1),
                "Share buyback",
            ],
        )
        client.commit()

        # Act
        result = corporate_actions_reader.get("600000")

        # Assert - Should return 3 actions ordered by announcement_date DESC
        assert len(result) == 3
        # SQLite returns dates as strings
        assert result["announcement_date"][0] == "2024-06-15"  # Most recent first
        assert result["announcement_date"][1] == "2024-05-01"
        assert result["announcement_date"][2] == "2024-04-01"

    def test_get_with_nullable_effective_date(
        self,
        corporate_actions_reader: CorporateActionsReader,
        in_memory_db: SQLitePool,
    ) -> None:
        """Test that get handles nullable effective_date correctly."""
        # Arrange
        client = SQLiteClient(in_memory_db)
        client.execute(
            """INSERT INTO corporate_actions
            (instrument_id, action_type, announcement_date,
             effective_date, description)
            VALUES (?, ?, ?, ?, ?)""",
            [
                "600000",
                "DIVIDEND",
                date(2024, 5, 1),
                None,
                "Cash dividend (no effective date)",
            ],
        )
        client.commit()

        # Act
        result = corporate_actions_reader.get("600000")

        # Assert
        assert len(result) == 1
        assert result["effective_date"][0] is None
