"""Unit tests for ExpressReader."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import polars as pl
import pytest
from ditto_data.stores.fundamental.forecast.express_reader import ExpressReader
from ditto_data.stores.sqlite_client import SQLiteClient
from ditto_infra.foundation import SQLitePool


@pytest.fixture
def in_memory_db(tmp_path: Path) -> SQLitePool:
    """Provide in-memory SQLite database with express table."""
    db_path = tmp_path / "test.db"

    pool = SQLitePool(str(db_path))
    pool.get_connection().execute(
        """CREATE TABLE IF NOT EXISTS express (
        instrument_id TEXT NOT NULL,
        report_date DATE NOT NULL,
        knowledge_date DATE NOT NULL,
        effective_from DATE NOT NULL,
        effective_to DATE,
        type TEXT,
        profit_range_min REAL,
        profit_range_max REAL,
        PRIMARY KEY (instrument_id, report_date, effective_from)
    )"""
    )
    return pool


@pytest.fixture
def express_reader(in_memory_db: SQLitePool) -> ExpressReader:
    """Provide ExpressReader with in-memory database."""
    return ExpressReader(SQLiteClient(in_memory_db))


@pytest.mark.unit
class TestExpressReader:
    """Test cases for ExpressReader."""

    def test_get_returns_data(
        self, express_reader: ExpressReader, in_memory_db: SQLitePool
    ) -> None:
        """Test that get returns data for valid query."""
        # Arrange
        client = SQLiteClient(in_memory_db)
        client.execute(
            """INSERT INTO express
            (instrument_id, report_date, knowledge_date,
             effective_from, effective_to, type,
             profit_range_min, profit_range_max)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                "600000",
                date(2024, 3, 31),
                date(2024, 4, 30),
                date(2024, 5, 1),
                None,
                "growth",
                100.0,
                200.0,
            ],
        )
        client.commit()

        # Act
        result = express_reader.get(600000, date(2024, 5, 15))

        # Assert
        assert len(result) == 1
        assert result["instrument_id"][0] == "600000"
        assert result["type"][0] == "growth"
        assert result["profit_range_min"][0] == 100.0
        assert result["profit_range_max"][0] == 200.0

    def test_get_empty_table(
        self,
        express_reader: ExpressReader,
    ) -> None:
        """Test that get returns empty DataFrame for empty table."""
        # Act
        result = express_reader.get(600000, date(2024, 5, 15))

        # Assert
        assert len(result) == 0
        assert isinstance(result, pl.DataFrame)

    def test_get_no_data(
        self, express_reader: ExpressReader, in_memory_db: SQLitePool
    ) -> None:
        """Test that get returns empty DataFrame for non-existent instrument."""
        # Arrange
        client = SQLiteClient(in_memory_db)
        client.execute(
            """INSERT INTO express
            (instrument_id, report_date, knowledge_date,
             effective_from, effective_to, type,
             profit_range_min, profit_range_max)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                "600001",
                date(2024, 3, 31),
                date(2024, 4, 30),
                date(2024, 5, 1),
                None,
                "growth",
                100.0,
                200.0,
            ],
        )
        client.commit()

        # Act
        result = express_reader.get(600000, date(2024, 5, 15))

        # Assert
        assert len(result) == 0

    def test_get_pit_query(
        self, express_reader: ExpressReader, in_memory_db: SQLitePool
    ) -> None:
        """Test PIT query returns correct version based on as_of_date."""
        # Arrange
        client = SQLiteClient(in_memory_db)
        # Insert first version (effective 2024-05-01 to 2024-06-01)
        client.execute(
            """INSERT INTO express
            (instrument_id, report_date, knowledge_date,
             effective_from, effective_to, type,
             profit_range_min, profit_range_max)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                "600000",
                date(2024, 3, 31),
                date(2024, 4, 30),
                date(2024, 5, 1),
                date(2024, 6, 1),
                "growth",
                100.0,
                200.0,
            ],
        )
        # Insert second version (effective from 2024-06-01)
        client.execute(
            """INSERT INTO express
            (instrument_id, report_date, knowledge_date,
             effective_from, effective_to, type,
             profit_range_min, profit_range_max)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                "600000",
                date(2024, 3, 31),
                date(2024, 5, 15),
                date(2024, 6, 1),
                None,
                "growth",
                150.0,
                250.0,
            ],
        )
        client.commit()

        # Act - Query before second version effective date
        result_old = express_reader.get(600000, date(2024, 5, 15))

        # Act - Query after second version effective date
        result_new = express_reader.get(600000, date(2024, 6, 15))

        # Assert
        assert len(result_old) == 1
        assert result_old["profit_range_min"][0] == 100.0

        assert len(result_new) == 1
        assert result_new["profit_range_min"][0] == 150.0

    def test_get_pit_query_excludes_expired_version(
        self, express_reader: ExpressReader, in_memory_db: SQLitePool
    ) -> None:
        """Test PIT query excludes version where effective_to == as_of_date."""
        # Arrange
        client = SQLiteClient(in_memory_db)
        # Version effective from 2024-05-01 to 2024-06-01
        # Note: effective_to = 2024-06-01 means version is NOT valid on 2024-06-01
        client.execute(
            """INSERT INTO express
            (instrument_id, report_date, knowledge_date,
             effective_from, effective_to, type,
             profit_range_min, profit_range_max)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                "600000",
                date(2024, 3, 31),
                date(2024, 4, 30),
                date(2024, 5, 1),
                date(2024, 6, 1),
                "growth",
                100.0,
                200.0,
            ],
        )
        client.commit()

        # Act - Query on effective_to date (version should be excluded)
        result = express_reader.get(600000, date(2024, 6, 1))

        # Assert
        assert len(result) == 0
