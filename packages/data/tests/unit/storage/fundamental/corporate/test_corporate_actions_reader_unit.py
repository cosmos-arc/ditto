"""Unit tests for CorporateActionsReader."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import polars as pl
import pytest
from ditto_data.storage.fundamental.corporate.corporate_actions_reader import (
    CorporateActionsReader,
)
from ditto_data.storage.fundamental.specs import CORPORATE_ACTIONS_SPEC
from ditto_data.storage.sqlite_client import SQLiteClient
from ditto_platform.foundation import SQLitePool

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
def corporate_actions_reader(in_memory_db: SQLitePool) -> CorporateActionsReader:
    """Provide CorporateActionsReader with in-memory database."""
    return CorporateActionsReader(SPEC, SQLiteClient(in_memory_db))


def _insert_row(
    db: SQLitePool,
    *,
    instrument_id: int,
    action_type: str,
    action_date: date,
    knowledge_date: date,
    effective_from: date,
    effective_to: date | None,
    description: str,
) -> None:
    """Helper to insert a corporate action row."""
    client = SQLiteClient(db)
    client.execute(
        """INSERT INTO corporate_actions
        (instrument_id, action_type, action_date,
         knowledge_date, effective_from, effective_to, description)
        VALUES (?, ?, ?, ?, ?, ?, ?)""",
        [
            instrument_id,
            action_type,
            action_date,
            knowledge_date,
            effective_from,
            effective_to,
            description,
        ],
    )
    client.commit()


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
        _insert_row(
            in_memory_db,
            instrument_id=600000,
            action_type="DIVIDEND",
            action_date=date(2024, 5, 1),
            knowledge_date=date(2024, 4, 25),
            effective_from=date(2024, 4, 25),
            effective_to=None,
            description="Cash dividend 0.5 per share",
        )

        # Act
        result = corporate_actions_reader.query(600000)

        # Assert
        assert len(result) == 1
        assert result["instrument_id"][0] == 600000
        assert result["action_type"][0] == "DIVIDEND"
        assert result["action_date"][0] == "2024-05-01"
        assert result["knowledge_date"][0] == "2024-04-25"
        assert result["effective_from"][0] == "2024-04-25"
        assert result["effective_to"][0] is None
        assert result["description"][0] == "Cash dividend 0.5 per share"

    def test_get_empty_table(
        self,
        corporate_actions_reader: CorporateActionsReader,
    ) -> None:
        """Test that get returns empty DataFrame for empty table."""
        # Act
        result = corporate_actions_reader.query(600000)

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
        _insert_row(
            in_memory_db,
            instrument_id=600001,
            action_type="DIVIDEND",
            action_date=date(2024, 5, 1),
            knowledge_date=date(2024, 4, 25),
            effective_from=date(2024, 4, 25),
            effective_to=None,
            description="Cash dividend 0.5 per share",
        )

        # Act
        result = corporate_actions_reader.query(600000)

        # Assert
        assert len(result) == 0

    def test_get_with_start_date(
        self,
        corporate_actions_reader: CorporateActionsReader,
        in_memory_db: SQLitePool,
    ) -> None:
        """Test that get filters by start_date correctly."""
        # Arrange
        _insert_row(
            in_memory_db,
            instrument_id=600000,
            action_type="DIVIDEND",
            action_date=date(2024, 4, 1),
            knowledge_date=date(2024, 3, 25),
            effective_from=date(2024, 3, 25),
            effective_to=None,
            description="April dividend",
        )
        _insert_row(
            in_memory_db,
            instrument_id=600000,
            action_type="SPLIT",
            action_date=date(2024, 5, 15),
            knowledge_date=date(2024, 5, 10),
            effective_from=date(2024, 5, 10),
            effective_to=None,
            description="Stock split 2:1",
        )

        # Act - Query from May 1st onwards
        result = corporate_actions_reader.query(600000, start_date=date(2024, 5, 1))

        # Assert - Should only include the split (action_date >= 2024-05-01)
        assert len(result) == 1
        assert result["action_type"][0] == "SPLIT"

    def test_get_with_end_date(
        self,
        corporate_actions_reader: CorporateActionsReader,
        in_memory_db: SQLitePool,
    ) -> None:
        """Test that get filters by end_date correctly."""
        # Arrange
        _insert_row(
            in_memory_db,
            instrument_id=600000,
            action_type="DIVIDEND",
            action_date=date(2024, 4, 1),
            knowledge_date=date(2024, 3, 25),
            effective_from=date(2024, 3, 25),
            effective_to=None,
            description="April dividend",
        )
        _insert_row(
            in_memory_db,
            instrument_id=600000,
            action_type="SPLIT",
            action_date=date(2024, 5, 15),
            knowledge_date=date(2024, 5, 10),
            effective_from=date(2024, 5, 10),
            effective_to=None,
            description="Stock split 2:1",
        )

        # Act - Query up to May 1st
        result = corporate_actions_reader.query(600000, end_date=date(2024, 5, 1))

        # Assert - Should only include the dividend (action_date <= 2024-05-01)
        assert len(result) == 1
        assert result["action_type"][0] == "DIVIDEND"

    def test_get_with_date_range(
        self,
        corporate_actions_reader: CorporateActionsReader,
        in_memory_db: SQLitePool,
    ) -> None:
        """Test that get filters by both start_date and end_date correctly."""
        # Arrange
        _insert_row(
            in_memory_db,
            instrument_id=600000,
            action_type="DIVIDEND",
            action_date=date(2024, 3, 1),
            knowledge_date=date(2024, 2, 25),
            effective_from=date(2024, 2, 25),
            effective_to=None,
            description="March dividend",
        )
        _insert_row(
            in_memory_db,
            instrument_id=600000,
            action_type="SPLIT",
            action_date=date(2024, 4, 15),
            knowledge_date=date(2024, 4, 10),
            effective_from=date(2024, 4, 10),
            effective_to=None,
            description="Stock split 2:1",
        )
        _insert_row(
            in_memory_db,
            instrument_id=600000,
            action_type="BUYBACK",
            action_date=date(2024, 5, 15),
            knowledge_date=date(2024, 5, 10),
            effective_from=date(2024, 5, 10),
            effective_to=None,
            description="Share buyback",
        )

        # Act - Query from April 1st to April 30th
        result = corporate_actions_reader.query(
            600000,
            start_date=date(2024, 4, 1),
            end_date=date(2024, 4, 30),
        )

        # Assert - Should only include the split (action_date in range)
        assert len(result) == 1
        assert result["action_type"][0] == "SPLIT"

    def test_get_multiple_actions(
        self,
        corporate_actions_reader: CorporateActionsReader,
        in_memory_db: SQLitePool,
    ) -> None:
        """Test that get returns multiple corporate actions ordered by date."""
        # Arrange
        _insert_row(
            in_memory_db,
            instrument_id=600000,
            action_type="DIVIDEND",
            action_date=date(2024, 5, 1),
            knowledge_date=date(2024, 4, 25),
            effective_from=date(2024, 4, 25),
            effective_to=None,
            description="May dividend",
        )
        _insert_row(
            in_memory_db,
            instrument_id=600000,
            action_type="SPLIT",
            action_date=date(2024, 6, 15),
            knowledge_date=date(2024, 6, 10),
            effective_from=date(2024, 6, 10),
            effective_to=None,
            description="Stock split 2:1",
        )
        _insert_row(
            in_memory_db,
            instrument_id=600000,
            action_type="BUYBACK",
            action_date=date(2024, 4, 1),
            knowledge_date=date(2024, 3, 25),
            effective_from=date(2024, 3, 25),
            effective_to=None,
            description="Share buyback",
        )

        # Act
        result = corporate_actions_reader.query(600000)

        # Assert - Should return 3 actions ordered by action_date DESC
        assert len(result) == 3
        assert result["action_date"][0] == "2024-06-15"  # Most recent first
        assert result["action_date"][1] == "2024-05-01"
        assert result["action_date"][2] == "2024-04-01"


@pytest.mark.unit
@pytest.mark.pit
class TestCorporateActionsReaderPIT:
    """Test PIT filtering for CorporateActionsReader."""

    def test_no_as_of_date_returns_all_versions(
        self,
        corporate_actions_reader: CorporateActionsReader,
        in_memory_db: SQLitePool,
    ) -> None:
        """Without as_of_date, all versions (including superseded) are returned."""
        # Arrange - same action with two versions
        _insert_row(
            in_memory_db,
            instrument_id=600000,
            action_type="DIVIDEND",
            action_date=date(2024, 5, 1),
            knowledge_date=date(2024, 4, 25),
            effective_from=date(2024, 4, 25),
            effective_to=date(2024, 5, 1),  # superseded
            description="Cash dividend 0.3 per share",
        )
        _insert_row(
            in_memory_db,
            instrument_id=600000,
            action_type="DIVIDEND",
            action_date=date(2024, 5, 1),
            knowledge_date=date(2024, 5, 1),
            effective_from=date(2024, 5, 1),
            effective_to=None,  # current version
            description="Cash dividend 0.5 per share (revised)",
        )

        # Act - no PIT filter
        result = corporate_actions_reader.query(600000)

        # Assert - both versions returned
        assert len(result) == 2

    def test_as_of_date_filters_to_valid_version(
        self,
        corporate_actions_reader: CorporateActionsReader,
        in_memory_db: SQLitePool,
    ) -> None:
        """as_of_date only returns the version effective at that date."""
        # Arrange - same action with two versions
        _insert_row(
            in_memory_db,
            instrument_id=600000,
            action_type="DIVIDEND",
            action_date=date(2024, 5, 1),
            knowledge_date=date(2024, 4, 25),
            effective_from=date(2024, 4, 25),
            effective_to=date(2024, 5, 1),  # superseded on May 1
            description="Cash dividend 0.3 per share",
        )
        _insert_row(
            in_memory_db,
            instrument_id=600000,
            action_type="DIVIDEND",
            action_date=date(2024, 5, 1),
            knowledge_date=date(2024, 5, 1),
            effective_from=date(2024, 5, 1),
            effective_to=None,  # current version
            description="Cash dividend 0.5 per share (revised)",
        )

        # Act - query as of April 28 (before second version)
        result = corporate_actions_reader.query(600000, as_of_date=date(2024, 4, 28))

        # Assert - only first version (effective_from <= Apr 28, effective_to > Apr 28)
        assert len(result) == 1
        assert result["description"][0] == "Cash dividend 0.3 per share"

    def test_as_of_date_at_boundary_excludes_expired(
        self,
        corporate_actions_reader: CorporateActionsReader,
        in_memory_db: SQLitePool,
    ) -> None:
        """as_of_date = effective_to should NOT include the expired version."""
        # Arrange
        _insert_row(
            in_memory_db,
            instrument_id=600000,
            action_type="DIVIDEND",
            action_date=date(2024, 5, 1),
            knowledge_date=date(2024, 4, 25),
            effective_from=date(2024, 4, 25),
            effective_to=date(2024, 5, 1),  # expires on May 1
            description="Old dividend",
        )
        _insert_row(
            in_memory_db,
            instrument_id=600000,
            action_type="DIVIDEND",
            action_date=date(2024, 5, 1),
            knowledge_date=date(2024, 5, 1),
            effective_from=date(2024, 5, 1),
            effective_to=None,
            description="Revised dividend",
        )

        # Act - query as of May 1 exactly
        result = corporate_actions_reader.query(600000, as_of_date=date(2024, 5, 1))

        # Assert - only the revised version (effective_to > May 1 via NULL)
        assert len(result) == 1
        assert result["description"][0] == "Revised dividend"

    def test_as_of_date_with_null_effective_to(
        self,
        corporate_actions_reader: CorporateActionsReader,
        in_memory_db: SQLitePool,
    ) -> None:
        """Versions with NULL effective_to are always valid (current version)."""
        # Arrange
        _insert_row(
            in_memory_db,
            instrument_id=600000,
            action_type="SPLIT",
            action_date=date(2024, 6, 1),
            knowledge_date=date(2024, 5, 25),
            effective_from=date(2024, 5, 25),
            effective_to=None,
            description="Stock split 2:1",
        )

        # Act - query far in the future
        result = corporate_actions_reader.query(600000, as_of_date=date(2030, 1, 1))

        # Assert - current version still valid
        assert len(result) == 1
        assert result["action_type"][0] == "SPLIT"

    def test_as_of_date_before_all_versions(
        self,
        corporate_actions_reader: CorporateActionsReader,
        in_memory_db: SQLitePool,
    ) -> None:
        """as_of_date before all effective_from dates returns nothing."""
        # Arrange
        _insert_row(
            in_memory_db,
            instrument_id=600000,
            action_type="DIVIDEND",
            action_date=date(2024, 5, 1),
            knowledge_date=date(2024, 4, 25),
            effective_from=date(2024, 4, 25),
            effective_to=None,
            description="Cash dividend",
        )

        # Act - query before effective_from
        result = corporate_actions_reader.query(600000, as_of_date=date(2024, 1, 1))

        # Assert
        assert len(result) == 0

    def test_as_of_date_combined_with_date_range(
        self,
        corporate_actions_reader: CorporateActionsReader,
        in_memory_db: SQLitePool,
    ) -> None:
        """as_of_date works together with start_date/end_date."""
        # Arrange
        _insert_row(
            in_memory_db,
            instrument_id=600000,
            action_type="DIVIDEND",
            action_date=date(2024, 3, 1),
            knowledge_date=date(2024, 2, 25),
            effective_from=date(2024, 2, 25),
            effective_to=None,
            description="March dividend",
        )
        _insert_row(
            in_memory_db,
            instrument_id=600000,
            action_type="SPLIT",
            action_date=date(2024, 4, 15),
            knowledge_date=date(2024, 4, 10),
            effective_from=date(2024, 4, 10),
            effective_to=None,
            description="Stock split 2:1",
        )
        _insert_row(
            in_memory_db,
            instrument_id=600000,
            action_type="BUYBACK",
            action_date=date(2024, 5, 15),
            knowledge_date=date(2024, 5, 10),
            effective_from=date(2024, 5, 10),
            effective_to=None,
            description="Share buyback",
        )

        # Act - date range + PIT (all are current, so PIT doesn't filter)
        result = corporate_actions_reader.query(
            600000,
            start_date=date(2024, 4, 1),
            end_date=date(2024, 4, 30),
            as_of_date=date(2024, 4, 30),
        )

        # Assert - only split falls in date range and is PIT-valid
        assert len(result) == 1
        assert result["action_type"][0] == "SPLIT"
